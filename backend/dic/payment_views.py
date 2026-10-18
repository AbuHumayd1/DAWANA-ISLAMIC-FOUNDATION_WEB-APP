import hashlib
import json
import uuid
from decimal import Decimal
from urllib.parse import urlparse

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .access import require_order_access
from .models import (
    PaymentAttempt,
    PaystackWebhookEvent,
    RegistrationOrder,
)
from .payments import (
    PaystackAPIError,
    PaystackClient,
    PaystackConfigurationError,
    PaystackTransportError,
    verify_webhook_signature,
)


UNRESOLVED_ATTEMPT_STATUSES = (
    PaymentAttempt.Status.INITIALIZING,
    PaymentAttempt.Status.PENDING,
    PaymentAttempt.Status.INITIALIZATION_UNKNOWN,
    PaymentAttempt.Status.VERIFICATION_PENDING,
    PaymentAttempt.Status.AMOUNT_MISMATCH,
)


class PaymentProviderUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Payment provider could not complete the request."
    default_code = "payment_provider_unavailable"

    def __init__(self, reference=None):
        detail = {"detail": self.default_detail}
        if reference:
            detail["payment_reference"] = reference
        super().__init__(detail)


def _order_for_access(request, public_id):
    order = (
        RegistrationOrder.objects.select_related("edition", "primary_registrant")
        .filter(public_id=public_id)
        .first()
    )
    if not order:
        raise NotFound("Order not found.")
    return require_order_access(request, order)


def _attempt_response(attempt, order, *, replayed=False):
    response = Response(
        {
            "order_id": str(order.public_id),
            "payment_reference": attempt.reference,
            "attempt_status": attempt.status,
            "payment_status": order.payment_status,
            "amount_kobo": attempt.amount_kobo,
            "currency": attempt.currency,
            "authorization_url": attempt.authorization_url or None,
            "idempotent_replay": replayed,
        },
        status=status.HTTP_200_OK,
    )
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _safe_provider_status(value):
    if not isinstance(value, str):
        return ""
    return "".join(
        character
        for character in value[:32]
        if character.isalnum() or character in "_-"
    )


def _mark_initialization_failure(attempt_id, failure_code, state):
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        if attempt.status == PaymentAttempt.Status.SUCCESSFUL:
            return attempt
        attempt.status = state
        attempt.failure_code = failure_code
        attempt.save(update_fields=("status", "failure_code", "updated_at"))
        return attempt


def _apply_verified_transaction(attempt_id, provider_data):
    with transaction.atomic():
        order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(
            pk=attempt_id
        )
        order = RegistrationOrder.objects.select_for_update().get(pk=order_id)
        attempt = (
            PaymentAttempt.objects.select_for_update()
            .get(pk=attempt_id)
        )
        if attempt.order_id != order.pk:
            raise PaymentAttempt.DoesNotExist

        if attempt.status in (
            PaymentAttempt.Status.SUCCESSFUL,
            PaymentAttempt.Status.DUPLICATE_SUCCESS,
        ):
            return attempt, order

        provider_status = _safe_provider_status(provider_data.get("status"))
        attempt.provider_status = provider_status
        attempt.verified_at = timezone.now()
        reference_matches = provider_data.get("reference") == attempt.reference
        amount = provider_data.get("amount")
        amount_matches = (
            isinstance(amount, int)
            and not isinstance(amount, bool)
            and amount == attempt.amount_kobo
        )
        currency_matches = provider_data.get("currency") == attempt.currency
        transaction_id = provider_data.get("id")
        transaction_id_value = (
            str(transaction_id)[:64]
            if isinstance(transaction_id, int) and not isinstance(transaction_id, bool)
            else None
        )
        reused_transaction_id = (
            transaction_id_value is not None
            and PaymentAttempt.objects.filter(
                provider_transaction_id=transaction_id_value
            )
            .exclude(pk=attempt.pk)
            .exists()
        )

        if (
            not reference_matches
            or not amount_matches
            or not currency_matches
            or reused_transaction_id
        ):
            attempt.status = PaymentAttempt.Status.AMOUNT_MISMATCH
            attempt.failure_code = (
                "provider_transaction_reused"
                if reused_transaction_id
                else "provider_data_mismatch"
            )
        else:
            attempt.provider_transaction_id = transaction_id_value
            if provider_status != "success":
                attempt.failure_code = ""
                if provider_status == "failed":
                    attempt.status = PaymentAttempt.Status.FAILED
                    if order.payment_status != RegistrationOrder.PaymentStatus.PAID:
                        order.payment_status = RegistrationOrder.PaymentStatus.FAILED
                        order.save(update_fields=("payment_status",))
                else:
                    attempt.status = PaymentAttempt.Status.PENDING
                    if order.payment_status != RegistrationOrder.PaymentStatus.PAID:
                        order.payment_status = RegistrationOrder.PaymentStatus.PENDING
                        order.save(update_fields=("payment_status",))
            elif (
                order.status == RegistrationOrder.Status.CANCELLED
                or order.payment_status == RegistrationOrder.PaymentStatus.REFUNDED
            ):
                attempt.status = PaymentAttempt.Status.AMOUNT_MISMATCH
                attempt.failure_code = "order_not_payable"
            elif order.payment_status == RegistrationOrder.PaymentStatus.PAID:
                attempt.status = PaymentAttempt.Status.DUPLICATE_SUCCESS
                attempt.failure_code = "duplicate_successful_charge"
            else:
                attempt.status = PaymentAttempt.Status.SUCCESSFUL
                attempt.failure_code = ""
                order.payment_status = RegistrationOrder.PaymentStatus.PAID
                order.status = RegistrationOrder.Status.CONFIRMED
                order.save(update_fields=("payment_status", "status"))

        attempt.save(
            update_fields=(
                "provider_status",
                "verified_at",
                "status",
                "failure_code",
                "provider_transaction_id",
                "updated_at",
            )
        )
        return attempt, order


def _verify_attempt(attempt, client):
    try:
        provider_data = client.verify_transaction(attempt.reference)
    except (PaystackTransportError, PaystackAPIError) as exc:
        with transaction.atomic():
            locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            if locked.status not in (
                PaymentAttempt.Status.SUCCESSFUL,
                PaymentAttempt.Status.DUPLICATE_SUCCESS,
            ):
                locked.status = PaymentAttempt.Status.VERIFICATION_PENDING
                locked.failure_code = (
                    "provider_rejected_verification"
                    if isinstance(exc, PaystackAPIError) and exc.definitive
                    else "verification_unavailable"
                )
                locked.save(
                    update_fields=("status", "failure_code", "updated_at")
                )
        raise PaymentProviderUnavailable(attempt.reference) from None
    return _apply_verified_transaction(attempt.pk, provider_data)


class PaymentInitializeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_payment_initiate"

    def post(self, request, public_id):
        order = _order_for_access(request, public_id)
        try:
            client = PaystackClient()
        except PaystackConfigurationError:
            return Response(
                {"detail": "Paystack test credentials are not configured correctly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            order = RegistrationOrder.objects.select_for_update().get(pk=order.pk)
            if order.status == RegistrationOrder.Status.CANCELLED:
                raise ValidationError("Cancelled orders cannot be paid.")
            if order.payment_status == RegistrationOrder.PaymentStatus.PAID:
                raise ValidationError("This order has already been paid.")
            if order.payment_status == RegistrationOrder.PaymentStatus.REFUNDED:
                raise ValidationError("Refunded orders cannot be paid.")

            unresolved = (
                PaymentAttempt.objects.select_for_update()
                .filter(order=order, status__in=UNRESOLVED_ATTEMPT_STATUSES)
                .first()
            )
            if unresolved:
                if (
                    unresolved.status == PaymentAttempt.Status.PENDING
                    and unresolved.authorization_url
                ):
                    return _attempt_response(unresolved, order, replayed=True)
                raise ValidationError(
                    {
                        "payment_reference": unresolved.reference,
                        "detail": (
                            "An existing payment attempt must be verified before "
                            "another can be started."
                        ),
                    }
                )

            total = Decimal(order.total_amount_ngn)
            amount_kobo_decimal = total * 100
            if total <= 0 or amount_kobo_decimal != amount_kobo_decimal.to_integral_value():
                raise ValidationError("The order does not have a payable NGN total.")
            amount_kobo = int(amount_kobo_decimal)
            first_item = (
                order.items.select_related("participant").order_by("id").first()
            )
            email = order.primary_registrant.email or (
                first_item.participant.email if first_item else ""
            )
            if not email:
                raise ValidationError(
                    "A registrant email address is required to initiate payment."
                )
            attempt = PaymentAttempt.objects.create(
                order=order,
                reference=f"DIC{uuid.uuid4().hex}",
                amount_kobo=amount_kobo,
                currency="NGN",
            )

        try:
            provider_data = client.initialize_transaction(
                email=email,
                amount_kobo=attempt.amount_kobo,
                reference=attempt.reference,
                callback_url=settings.PAYSTACK_CALLBACK_URL,
                metadata={
                    "order_id": str(order.public_id),
                    "payment_attempt_id": str(attempt.pk),
                },
            )
            authorization_url = provider_data.get("authorization_url")
            provider_reference = provider_data.get("reference")
            try:
                parsed_url = (
                    urlparse(authorization_url)
                    if isinstance(authorization_url, str)
                    else None
                )
                checkout_port = parsed_url.port if parsed_url else None
            except ValueError:
                parsed_url = None
                checkout_port = None
            is_checkout_url = (
                parsed_url is not None
                and parsed_url.scheme == "https"
                and parsed_url.hostname == "checkout.paystack.com"
                and not parsed_url.username
                and not parsed_url.password
                and checkout_port in (None, 443)
            )
            if not is_checkout_url or provider_reference != attempt.reference:
                _mark_initialization_failure(
                    attempt.pk,
                    "invalid_provider_initialization",
                    PaymentAttempt.Status.INITIALIZATION_UNKNOWN,
                )
                raise PaymentProviderUnavailable(attempt.reference)
        except PaystackTransportError:
            attempt = _mark_initialization_failure(
                attempt.pk,
                "initialization_unavailable",
                PaymentAttempt.Status.INITIALIZATION_UNKNOWN,
            )
            raise PaymentProviderUnavailable(attempt.reference) from None
        except PaystackAPIError as exc:
            state = (
                PaymentAttempt.Status.FAILED
                if exc.definitive
                else PaymentAttempt.Status.INITIALIZATION_UNKNOWN
            )
            attempt = _mark_initialization_failure(
                attempt.pk,
                "provider_rejected_initialization"
                if exc.definitive
                else "initialization_unavailable",
                state,
            )
            raise PaymentProviderUnavailable(attempt.reference) from None

        with transaction.atomic():
            attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            order = RegistrationOrder.objects.select_for_update().get(pk=order.pk)
            if attempt.status == PaymentAttempt.Status.INITIALIZING:
                attempt.status = PaymentAttempt.Status.PENDING
                attempt.authorization_url = authorization_url
                attempt.save(
                    update_fields=("status", "authorization_url", "updated_at")
                )
        return _attempt_response(attempt, order)


class PaymentVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_payment_verify"

    def post(self, request, public_id, reference):
        order = _order_for_access(request, public_id)
        attempt = PaymentAttempt.objects.filter(
            order=order,
            reference=reference,
        ).first()
        if not attempt:
            raise NotFound("Payment attempt not found.")
        if attempt.status in (
            PaymentAttempt.Status.SUCCESSFUL,
            PaymentAttempt.Status.DUPLICATE_SUCCESS,
        ):
            return _attempt_response(attempt, order, replayed=True)

        try:
            client = PaystackClient()
        except PaystackConfigurationError:
            return Response(
                {"detail": "Paystack test credentials are not configured correctly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        attempt, order = _verify_attempt(attempt, client)
        return _attempt_response(attempt, order)


class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_paystack_webhook"

    def post(self, request):
        if len(request.body) > 1_048_576:
            return Response(
                {"detail": "Webhook payload is too large."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            client = PaystackClient()
        except PaystackConfigurationError:
            return Response(
                {"detail": "Paystack test credentials are not configured correctly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        signature = request.headers.get("X-Paystack-Signature", "")
        if not verify_webhook_signature(request.body, signature, client.secret_key):
            return Response(
                {"detail": "Invalid webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                {"detail": "Invalid webhook payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return Response(
                {"detail": "Invalid webhook payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = payload.get("event")
        data = payload["data"]
        reference = data.get("reference")
        if not isinstance(event_type, str) or not isinstance(reference, str):
            return Response(
                {"detail": "Invalid webhook payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload_digest = hashlib.sha256(request.body).hexdigest()
        try:
            event, created = PaystackWebhookEvent.objects.get_or_create(
                payload_digest=payload_digest,
                defaults={
                    "event_type": event_type[:80],
                    "reference": reference[:80],
                },
            )
        except IntegrityError:
            event = PaystackWebhookEvent.objects.get(
                payload_digest=payload_digest
            )
            created = False

        if not created and event.processing_status in (
            PaystackWebhookEvent.ProcessingStatus.PROCESSED,
            PaystackWebhookEvent.ProcessingStatus.IGNORED,
        ):
            return Response({"received": True, "duplicate": True})

        attempt = PaymentAttempt.objects.filter(reference=reference).first()
        event.payment_attempt = attempt
        if event_type != "charge.success" or not attempt:
            event.processing_status = PaystackWebhookEvent.ProcessingStatus.IGNORED
            event.processed_at = timezone.now()
            event.save(update_fields=("payment_attempt", "processing_status", "processed_at"))
            return Response({"received": True})

        try:
            attempt, _ = _verify_attempt(attempt, client)
        except PaymentProviderUnavailable:
            event.processing_status = PaystackWebhookEvent.ProcessingStatus.RETRY
            event.save(update_fields=("payment_attempt", "processing_status"))
            return Response(
                {"detail": "Payment verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        event.payment_attempt = attempt
        event.processing_status = PaystackWebhookEvent.ProcessingStatus.PROCESSED
        event.processed_at = timezone.now()
        event.save(
            update_fields=("payment_attempt", "processing_status", "processed_at")
        )
        return Response({"received": True})
