import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import CharField, F, Func, Q, Value
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (
    RegistrationOrder,
    RegistrationRecoveryChallenge,
    RegistrationRecoveryGrant,
    RegistrationRecoveryGrantOrder,
    RegistrationRecoveryRateLimit,
)
from .recovery import (
    available_channels,
    channel_available,
    encrypt_delivery_payload,
    normalize_email,
    normalize_phone,
    phone_match_digits,
    whatsapp_support_url,
)
from .security import digest_value, order_access_token_expiry


CODE_TTL = timedelta(minutes=10)
GRANT_TTL = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=60)
RATE_WINDOW = timedelta(hours=1)
MAX_REQUESTS_PER_CONTACT = 5
MAX_REQUESTS_PER_IP = 30
MAX_CODE_ATTEMPTS = 5

GENERIC_REQUEST_MESSAGE = (
    "If the contact details match an eligible registration and this channel is "
    "available, a recovery code will be sent. Do not share the code with anyone."
)
GENERIC_FAILURE_MESSAGE = (
    "The request could not be completed. Check the contact details and try again."
)


class RecoveryRateLimited(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Please wait before requesting another recovery code."
    default_code = "recovery_rate_limited"


class RecoveryChannelUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "This recovery channel is not currently available."
    default_code = "recovery_channel_unavailable"


def _digest(salt, value):
    return salted_hmac(salt, value).hexdigest()


def _contact_digest(channel, contact):
    return _digest("dic.registration-recovery.contact", f"{channel}:{contact}")


def _code_digest(challenge_id, code):
    return _digest("dic.registration-recovery.code", f"{challenge_id}:{code}")


def _token_digest(token):
    return _digest("dic.registration-recovery.grant", token)


def _normalize_contact(channel, value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({"contact": "Enter an email address or phone number."})
    if channel == RegistrationRecoveryChallenge.Channel.EMAIL:
        normalized = normalize_email(value)
        try:
            validate_email(normalized)
        except DjangoValidationError as exc:
            raise ValidationError({"contact": "Enter a valid email address."}) from exc
        return normalized
    if channel in (
        RegistrationRecoveryChallenge.Channel.SMS,
        RegistrationRecoveryChallenge.Channel.WHATSAPP,
    ):
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise ValidationError({"contact": str(exc)}) from exc
    raise ValidationError({"channel": "Choose a supported recovery channel."})


def _matching_orders(channel, contact):
    orders = RegistrationOrder.objects.exclude(
        status=RegistrationOrder.Status.CANCELLED
    )
    if channel == RegistrationRecoveryChallenge.Channel.EMAIL:
        normalized = normalize_email(contact)
        return orders.annotate(
            participant_email=Func(
                F("items__participant__email"),
                function="LOWER",
                output_field=CharField(),
            ),
            registrant_email=Func(
                F("primary_registrant__email"),
                function="LOWER",
                output_field=CharField(),
            ),
        ).filter(
            Q(participant_email=normalized) | Q(registrant_email=normalized)
        ).distinct()

    candidates = phone_match_digits(contact)
    digits = lambda field: Func(
        F(field),
        Value(r"[^0-9]"),
        Value(""),
        Value("g"),
        function="regexp_replace",
        output_field=CharField(),
    )
    return orders.annotate(
        participant_phone=digits("items__participant__phone"),
        registrant_phone=digits("primary_registrant__phone"),
    ).filter(
        Q(participant_phone__in=candidates)
        | Q(registrant_phone__in=candidates)
    ).distinct()


def _rate_key(kind, value):
    return _digest("dic.registration-recovery.rate-limit", f"{kind}:{value}")


def _consume_rate_limit(key, maximum, now, *, cooldown=False):
    bucket, _ = RegistrationRecoveryRateLimit.objects.get_or_create(
        key_digest=key,
        defaults={"window_started_at": now},
    )
    bucket = RegistrationRecoveryRateLimit.objects.select_for_update().get(pk=bucket.pk)
    if bucket.window_started_at + RATE_WINDOW <= now:
        bucket.window_started_at = now
        bucket.request_count = 0
        bucket.cooldown_until = None
    if bucket.cooldown_until and bucket.cooldown_until > now:
        raise RecoveryRateLimited()
    if bucket.request_count >= maximum:
        raise RecoveryRateLimited()
    bucket.request_count += 1
    if cooldown:
        bucket.cooldown_until = now + RESEND_COOLDOWN
    bucket.save(
        update_fields=(
            "window_started_at",
            "request_count",
            "cooldown_until",
            "updated_at",
        )
    )


def _consume_request_limits(channel, contact, request, now):
    contact_hash = _contact_digest(channel, contact)
    remote_address = request.META.get("REMOTE_ADDR", "")
    ip_hash = _digest("dic.registration-recovery.ip", remote_address or "unknown")
    with transaction.atomic():
        _consume_rate_limit(
            _rate_key("contact", contact_hash),
            MAX_REQUESTS_PER_CONTACT,
            now,
            cooldown=True,
        )
        _consume_rate_limit(
            _rate_key("ip", ip_hash),
            MAX_REQUESTS_PER_IP,
            now,
        )
    return contact_hash


def _challenge_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _request_challenge(channel, contact, request):
    now = timezone.now()
    contact_hash = _consume_request_limits(channel, contact, request, now)
    code = _challenge_code()
    with transaction.atomic():
        RegistrationRecoveryChallenge.objects.filter(
            contact_digest=contact_hash,
            channel=channel,
            consumed_at__isnull=True,
            expires_at__gt=now,
        ).select_for_update().update(
            consumed_at=now,
            encrypted_delivery_payload="",
        )
        challenge = RegistrationRecoveryChallenge.objects.create(
            contact_digest=contact_hash,
            channel=channel,
            code_digest="",
            expires_at=now + CODE_TTL,
            resend_after=now + RESEND_COOLDOWN,
            encrypted_delivery_payload=encrypt_delivery_payload(
                channel,
                contact,
                code,
            ),
        )
        challenge.code_digest = _code_digest(challenge.pk, code)
        challenge.save(update_fields=("code_digest",))
    return challenge


def _resend_challenge(challenge_id, channel, contact, request):
    now = timezone.now()
    contact_hash = _consume_request_limits(channel, contact, request, now)
    with transaction.atomic():
        challenge = (
            RegistrationRecoveryChallenge.objects.select_for_update()
            .filter(
                pk=challenge_id,
                channel=channel,
                contact_digest=contact_hash,
                consumed_at__isnull=True,
                expires_at__gt=now,
            )
            .first()
        )
        if (
            not challenge
            or challenge.resend_after > now
            or challenge.delivery_status
            == RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING
        ):
            raise RecoveryRateLimited()
        code = _challenge_code()
        challenge.code_digest = _code_digest(challenge.pk, code)
        challenge.encrypted_delivery_payload = encrypt_delivery_payload(
            channel,
            contact,
            code,
        )
        challenge.expires_at = now + CODE_TTL
        challenge.resend_after = now + RESEND_COOLDOWN
        challenge.attempts = 0
        challenge.delivery_status = RegistrationRecoveryChallenge.DeliveryStatus.QUEUED
        challenge.delivery_started_at = None
        challenge.orders.clear()
        challenge.save(
            update_fields=(
                "code_digest",
                "encrypted_delivery_payload",
                "expires_at",
                "resend_after",
                "attempts",
                "delivery_status",
                "delivery_started_at",
            )
        )
    return challenge


def _order_recovery_summary(order):
    return {
        "order_id": str(order.public_id),
        "edition_name": order.edition.name,
        "status": order.status,
        "payment_status": order.payment_status,
        "total_amount_ngn": str(order.total_amount_ngn),
        "participant_count": order.items.count(),
        "created_at": order.created_at,
        "items": _order_recovery_items(order),
    }


def _order_recovery_items(order):
    revision_items = {}
    if order.current_price_revision_id:
        revision_items = {
            price_item.order_item_id: price_item
            for price_item in order.current_price_revision.items.all()
        }
    return [
        {
            "category_name": (
                revision_items[item.pk].category_name_snapshot
                if item.pk in revision_items
                else item.category_name_snapshot
            ),
            "fee_ngn": str(
                revision_items[item.pk].fee_snapshot_ngn
                if item.pk in revision_items
                else item.fee_snapshot_ngn
            ),
            "price_type": (
                revision_items[item.pk].price_type
                if item.pk in revision_items
                else "regular"
            ),
        }
        for item in order.items.all()
    ]


def _authorized_grant(request, *, lock=False):
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise NotFound(GENERIC_FAILURE_MESSAGE)
    query = RegistrationRecoveryGrant.objects
    if lock:
        query = query.select_for_update()
    grant = query.filter(
        token_digest=_token_digest(token.strip()),
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if not grant:
        raise NotFound(GENERIC_FAILURE_MESSAGE)
    return grant


class RecoveryChannelsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_channels"

    def get(self, request):
        support_url = whatsapp_support_url()
        return Response(
            {
                "channels": [
                    {
                        "id": channel.key,
                        "label": channel.label,
                        "available": channel.available,
                    }
                    for channel in available_channels()
                ],
                "whatsapp_support_url": support_url,
            }
        )


class RecoveryChallengeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_request"

    def post(self, request):
        channel = request.data.get("channel")
        if channel not in RegistrationRecoveryChallenge.Channel.values:
            raise ValidationError({"channel": "Choose a supported recovery channel."})
        if not channel_available(channel):
            raise RecoveryChannelUnavailable()
        contact = _normalize_contact(channel, request.data.get("contact"))
        challenge = _request_challenge(channel, contact, request)
        response = Response(
            {
                "challenge_id": str(challenge.pk),
                "expires_in": int(CODE_TTL.total_seconds()),
                "resend_after": int(RESEND_COOLDOWN.total_seconds()),
                "message": GENERIC_REQUEST_MESSAGE,
            },
            status=status.HTTP_202_ACCEPTED,
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RecoveryResendView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_request"

    def post(self, request, challenge_id):
        try:
            parsed_id = uuid.UUID(str(challenge_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise NotFound(GENERIC_FAILURE_MESSAGE) from exc
        channel = request.data.get("channel")
        if channel not in RegistrationRecoveryChallenge.Channel.values:
            raise ValidationError({"channel": "Choose a supported recovery channel."})
        if not channel_available(channel):
            raise RecoveryChannelUnavailable()
        contact = _normalize_contact(channel, request.data.get("contact"))
        challenge = _resend_challenge(parsed_id, channel, contact, request)
        response = Response(
            {
                "challenge_id": str(challenge.pk),
                "expires_in": int(CODE_TTL.total_seconds()),
                "resend_after": int(RESEND_COOLDOWN.total_seconds()),
                "message": GENERIC_REQUEST_MESSAGE,
            },
            status=status.HTTP_202_ACCEPTED,
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RecoveryVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_verify"

    def post(self, request, challenge_id):
        try:
            parsed_id = uuid.UUID(str(challenge_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise NotFound(GENERIC_FAILURE_MESSAGE) from exc
        code = request.data.get("code")
        if not isinstance(code, str) or not code.isdigit() or len(code) != 6:
            raise ValidationError({"code": "Enter the six-digit verification code."})

        now = timezone.now()
        invalid_code = False
        with transaction.atomic():
            challenge = (
                RegistrationRecoveryChallenge.objects.select_for_update()
                .filter(pk=parsed_id)
                .first()
            )
            if (
                not challenge
                or challenge.consumed_at
                or challenge.expires_at <= now
                or challenge.delivery_status
                != RegistrationRecoveryChallenge.DeliveryStatus.SENT
                or challenge.attempts >= MAX_CODE_ATTEMPTS
            ):
                raise ValidationError(GENERIC_FAILURE_MESSAGE)
            if not hmac.compare_digest(
                challenge.code_digest,
                _code_digest(challenge.pk, code),
            ):
                challenge.attempts += 1
                if challenge.attempts >= MAX_CODE_ATTEMPTS:
                    challenge.consumed_at = now
                challenge.save(update_fields=("attempts", "consumed_at"))
                invalid_code = True
            else:
                challenge.consumed_at = now
                challenge.save(update_fields=("consumed_at",))
                grant_token = secrets.token_urlsafe(32)
                grant = RegistrationRecoveryGrant.objects.create(
                    token_digest=_token_digest(grant_token),
                    challenge=challenge,
                    expires_at=now + GRANT_TTL,
                )
                grant.orders.set(
                    challenge.orders.exclude(
                        status=RegistrationOrder.Status.CANCELLED
                    )
                )
        if invalid_code:
            raise ValidationError(GENERIC_FAILURE_MESSAGE)

        response = Response(
            {
                "recovery_grant": grant_token,
                "expires_in": int(GRANT_TTL.total_seconds()),
            }
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RecoveryOrdersView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_orders"

    def get(self, request):
        grant = _authorized_grant(request)
        orders = (
            grant.orders.exclude(status=RegistrationOrder.Status.CANCELLED)
            .select_related("edition", "current_price_revision")
            .prefetch_related("items")
            .prefetch_related("current_price_revision__items")
            .order_by("-created_at")
        )
        response = Response(
            {"orders": [_order_recovery_summary(order) for order in orders]}
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RecoveryRestoreOrderView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_recovery_restore"

    def post(self, request, public_id):
        with transaction.atomic():
            grant = _authorized_grant(request, lock=True)
            order = (
                RegistrationOrder.objects.select_for_update(of=("self",))
                .select_related("edition", "current_price_revision")
                .prefetch_related(
                    "items",
                    "current_price_revision__items",
                )
                .filter(public_id=public_id)
                .first()
            )
            grant_order = None
            if order:
                grant_order = (
                    RegistrationRecoveryGrantOrder.objects.select_for_update()
                    .filter(
                        grant=grant,
                        order=order,
                        redeemed_at__isnull=True,
                    )
                    .first()
                )
            if (
                not order
                or order.status == RegistrationOrder.Status.CANCELLED
                or order.access_token_revoked_at is not None
                or not grant_order
            ):
                raise NotFound(GENERIC_FAILURE_MESSAGE)
            access_token = secrets.token_urlsafe(32)
            order.access_token_digest = digest_value(access_token)
            order.access_token_expires_at = order_access_token_expiry()
            order.save(
                update_fields=(
                    "access_token_digest",
                    "access_token_expires_at",
                )
            )
            grant_order.redeemed_at = timezone.now()
            grant_order.save(update_fields=("redeemed_at",))
            summary = _order_recovery_summary(order)

        response = Response(
            {
                "access_token": access_token,
                "order": summary,
            }
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
