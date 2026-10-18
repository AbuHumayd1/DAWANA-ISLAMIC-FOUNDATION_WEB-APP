import hmac
import json
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .access import require_order_access
from .models import (
    CampEdition,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)
from .pricing import (
    PricingConfigurationError,
    create_price_revision,
    price_for_category,
)
from .security import digest_value, new_order_access_token, order_access_token_expiry
from .serializers import (
    ActiveEditionSerializer,
    RegistrationOrderCreateSerializer,
    RegistrationOrderReadSerializer,
)


class IdempotencyConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This idempotency key has already been used for another request."
    default_code = "idempotency_conflict"


def _registration_is_open(edition, today):
    return (
        edition.registration_status == CampEdition.RegistrationStatus.OPEN
        and edition.registration_open_date is not None
        and edition.registration_close_date is not None
        and edition.registration_open_date <= today <= edition.registration_close_date
        and edition.pricing_configuration_is_complete
    )


def _age_on(birth_date, reference_date):
    return reference_date.year - birth_date.year - (
        (reference_date.month, reference_date.day)
        < (birth_date.month, birth_date.day)
    )


def _idempotency_digest(request):
    value = request.headers.get("Idempotency-Key", "").strip()
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValidationError(
            "A cryptographically random UUIDv4 Idempotency-Key header is required."
        )
    if parsed.version != 4:
        raise ValidationError(
            "A cryptographically random UUIDv4 Idempotency-Key header is required."
        )
    return digest_value(str(parsed))


def _request_fingerprint(validated_data):
    normalized = json.dumps(
        validated_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return salted_hmac(
        "dic.registration-order-request",
        normalized,
    ).hexdigest()


def _order_summary(order, access_token, replayed=False):
    items = list(order.items.select_related("category").all())
    revision_items = {}
    if order.current_price_revision_id:
        revision_items = {
            item.order_item_id: item
            for item in order.current_price_revision.items.all()
        }
    return {
        "order_id": str(order.public_id),
        "access_token": access_token,
        "status": order.status,
        "payment_status": order.payment_status,
        "currency": "NGN",
        "total_amount_ngn": str(order.total_amount_ngn),
        "participant_count": len(items),
        "items": [
            {
                "category_name": item.category_name_snapshot,
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
            for item in items
        ],
        "idempotent_replay": replayed,
    }


def _create_order(*, key_digest, fingerprint, payload):
    with transaction.atomic():
        existing = (
            RegistrationOrder.objects.select_for_update()
            .filter(idempotency_key_digest=key_digest)
            .first()
        )
        if existing:
            if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
                raise IdempotencyConflict()
            if existing.access_token_revoked_at is not None:
                raise IdempotencyConflict("Order access has been revoked.")
            token = new_order_access_token()
            existing.access_token_digest = digest_value(token)
            existing.access_token_expires_at = order_access_token_expiry()
            existing.save(
                update_fields=(
                    "access_token_digest",
                    "access_token_expires_at",
                )
            )
            return existing, token, True

        edition = (
            CampEdition.objects.select_for_update()
            .filter(is_active=True)
            .first()
        )
        today = timezone.localdate()
        if not edition or not _registration_is_open(edition, today):
            raise ValidationError("DIC registration is not currently open.")
        if edition.pricing_configuration_errors():
            raise ValidationError(
                {
                    "pricing": (
                        "DIC pricing is incomplete. Registration cannot be opened "
                        "until an administrator configures approved fees and dates."
                    )
                }
            )

        participant_data = payload["participants"]
        category_ids = {item["category_id"] for item in participant_data}
        categories = {
            category.pk: category
            for category in RegistrationCategory.objects.select_for_update().filter(
                pk__in=category_ids,
                edition=edition,
                is_active=True,
            )
        }
        if len(categories) != len(category_ids):
            raise ValidationError(
                "One or more selected categories are unavailable for the active edition."
            )

        prices_by_category = {}
        price_at = timezone.now()
        for index, data in enumerate(participant_data):
            category = categories[data["category_id"]]
            try:
                prices_by_category[category.pk] = price_for_category(
                    category,
                    price_at,
                )
            except PricingConfigurationError as exc:
                raise ValidationError({"pricing": str(exc)}) from exc
            age = _age_on(data["date_of_birth"], today)
            if category.minimum_age is not None and age < category.minimum_age:
                raise ValidationError(
                    f"Participant {index + 1} does not meet the selected category's "
                    "minimum age eligibility."
                )
            if category.maximum_age is not None and age > category.maximum_age:
                raise ValidationError(
                    f"Participant {index + 1} does not meet the selected category's "
                    "maximum age eligibility."
                )

        registrant_data = payload.get("primary_registrant", {})
        registrant = PrimaryRegistrant.objects.create(**registrant_data)
        public_id = uuid.uuid4()
        token = new_order_access_token()
        order = RegistrationOrder.objects.create(
            public_id=public_id,
            primary_registrant=registrant,
            edition=edition,
            idempotency_key_digest=key_digest,
            request_fingerprint=fingerprint,
            access_token_digest=digest_value(token),
            access_token_expires_at=order_access_token_expiry(),
        )

        prices = []
        for data in participant_data:
            participant_fields = {
                key: value for key, value in data.items() if key != "category_id"
            }
            participant = Participant.objects.create(**participant_fields)
            category = categories[data["category_id"]]
            price = prices_by_category[category.pk]
            item = RegistrationOrderItem.objects.create(
                order=order,
                participant=participant,
                category=category,
                fee_snapshot_ngn=price["fee_ngn"],
            )
            prices.append({"order_item": item, **price})

        create_price_revision(order, prices, accepted_at=price_at)

        return order, token, False


class RegistrationOptionsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_registration_options"

    def get(self, request):
        edition = (
            CampEdition.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "registration_categories",
                    queryset=RegistrationCategory.objects.filter(is_active=True),
                )
            )
            .first()
        )
        if not edition:
            raise NotFound("No active DIC edition is configured.")
        response = Response(ActiveEditionSerializer(edition).data)
        response["Cache-Control"] = "no-store"
        return response


class RegistrationOrderCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_registration_create"

    def post(self, request):
        serializer = RegistrationOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        key_digest = _idempotency_digest(request)
        fingerprint = _request_fingerprint(serializer.validated_data)
        try:
            order, token, replayed = _create_order(
                key_digest=key_digest,
                fingerprint=fingerprint,
                payload=serializer.validated_data,
            )
        except IntegrityError:
            existing = RegistrationOrder.objects.filter(
                idempotency_key_digest=key_digest
            ).first()
            if not existing:
                raise
            if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
                raise IdempotencyConflict()
            if existing.access_token_revoked_at is not None:
                raise IdempotencyConflict("Order access has been revoked.")
            token = new_order_access_token()
            existing.access_token_digest = digest_value(token)
            existing.access_token_expires_at = order_access_token_expiry()
            existing.save(
                update_fields=(
                    "access_token_digest",
                    "access_token_expires_at",
                )
            )
            order, replayed = existing, True

        response = Response(
            _order_summary(order, token, replayed),
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RegistrationOrderDetailView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "dic_order_retrieve"

    def get(self, request, public_id):
        order = (
            RegistrationOrder.objects.select_related(
                "edition",
                "primary_registrant",
            )
            .prefetch_related("items")
            .prefetch_related("current_price_revision__items")
            .filter(public_id=public_id)
            .first()
        )
        if not order:
            raise NotFound("Order not found.")

        require_order_access(request, order)

        response = Response(RegistrationOrderReadSerializer(order).data)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
