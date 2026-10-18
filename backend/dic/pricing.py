from decimal import Decimal

from django.core import signing
from django.utils import timezone

from .models import (
    CampEdition,
    RegistrationCategory,
    RegistrationOrderPriceItem,
    RegistrationOrderPriceRevision,
)


QUOTE_MAX_AGE_SECONDS = 300
QUOTE_SIGNING_SALT = "dic.registration.order.repricing"


class PricingConfigurationError(Exception):
    pass


def price_for_category(category, at):
    if category.fee_ngn is None or category.fee_ngn <= 0:
        raise PricingConfigurationError(
            "A positive regular fee is not configured for this registration category."
        )
    edition = category.edition
    if category.early_bird_fee_ngn is not None:
        if edition.early_bird_cutoff_at is None:
            raise PricingConfigurationError(
                "The edition early-bird cutoff is not configured."
            )
        if (
            category.early_bird_fee_ngn <= 0
            or category.early_bird_fee_ngn >= category.fee_ngn
        ):
            raise PricingConfigurationError(
                "The early-bird fee must be lower than the regular fee."
            )
    early_is_current = (
        category.early_bird_fee_ngn is not None
        and edition.early_bird_cutoff_at is not None
        and at < edition.early_bird_cutoff_at
    )
    return {
        "category_name": category.name,
        "early_bird_fee_ngn": category.early_bird_fee_ngn,
        "regular_fee_ngn": category.fee_ngn,
        "fee_ngn": (
            category.early_bird_fee_ngn
            if early_is_current
            else category.fee_ngn
        ),
        "price_type": (
            RegistrationOrderPriceItem.PriceType.EARLY_BIRD
            if early_is_current
            else RegistrationOrderPriceItem.PriceType.REGULAR
        ),
    }


def current_order_prices(order, at=None):
    at = at or timezone.now()
    return [
        {
            "order_item": item,
            **price_for_category(item.category, at),
        }
        for item in order.items.select_related("category", "category__edition")
        .order_by("id")
    ]


def lock_order_pricing_configuration(order):
    edition = CampEdition.objects.select_for_update().get(pk=order.edition_id)
    category_ids = order.items.values_list("category_id", flat=True)
    list(
        RegistrationCategory.objects.select_for_update().filter(
            pk__in=category_ids
        )
    )
    order.edition = edition
    return edition


def revision_matches_current(revision, prices):
    if (
        revision is None
        or revision.early_bird_cutoff_at != revision.order.edition.early_bird_cutoff_at
    ):
        return False
    existing = list(revision.items.order_by("order_item_id"))
    if len(existing) != len(prices):
        return False
    return all(
        line.order_item_id == price["order_item"].pk
        and line.category_name_snapshot == price["category_name"]
        and line.early_bird_fee_snapshot_ngn == price["early_bird_fee_ngn"]
        and line.regular_fee_snapshot_ngn == price["regular_fee_ngn"]
        and line.fee_snapshot_ngn == price["fee_ngn"]
        and line.price_type == price["price_type"]
        for line, price in zip(existing, prices)
    )


def create_price_revision(order, prices, *, accepted_at):
    revision_number = (
        order.price_revisions.order_by("-revision_number")
        .values_list("revision_number", flat=True)
        .first()
        or 0
    ) + 1
    total = sum(
        (price["fee_ngn"] for price in prices),
        Decimal("0.00"),
    )
    revision = RegistrationOrderPriceRevision.objects.create(
        order=order,
        revision_number=revision_number,
        early_bird_cutoff_at=order.edition.early_bird_cutoff_at,
        total_amount_ngn=total,
        created_at=timezone.now(),
        accepted_at=accepted_at,
    )
    RegistrationOrderPriceItem.objects.bulk_create(
        [
            RegistrationOrderPriceItem(
                revision=revision,
                order_item=price["order_item"],
                category_name_snapshot=price["category_name"],
                early_bird_fee_snapshot_ngn=price["early_bird_fee_ngn"],
                regular_fee_snapshot_ngn=price["regular_fee_ngn"],
                fee_snapshot_ngn=price["fee_ngn"],
                price_type=price["price_type"],
            )
            for price in prices
        ]
    )
    order.current_price_revision = revision
    order.save(update_fields=("current_price_revision",))
    return revision


def quote_payload(order, prices):
    return {
        "order_id": str(order.public_id),
        "current_revision": (
            order.current_price_revision.revision_number
            if order.current_price_revision_id
            else 0
        ),
        "edition_cutoff": (
            order.edition.early_bird_cutoff_at.isoformat()
            if order.edition.early_bird_cutoff_at
            else None
        ),
        "total_amount_ngn": str(
            sum((price["fee_ngn"] for price in prices), Decimal("0.00"))
        ),
        "items": [
            {
                "order_item_id": price["order_item"].pk,
                "category_name": price["category_name"],
                "fee_ngn": str(price["fee_ngn"]),
                "price_type": price["price_type"],
            }
            for price in prices
        ],
    }


def sign_repricing_quote(order, prices):
    return signing.dumps(
        quote_payload(order, prices),
        salt=QUOTE_SIGNING_SALT,
        compress=True,
    )


def verify_repricing_quote(token, order, prices):
    try:
        submitted = signing.loads(
            token,
            salt=QUOTE_SIGNING_SALT,
            max_age=QUOTE_MAX_AGE_SECONDS,
        )
    except (signing.BadSignature, TypeError, ValueError):
        return False
    current_payload = quote_payload(order, prices)
    if submitted == current_payload:
        return True
    if order.current_price_revision_id:
        current_payload["current_revision"] = (
            order.current_price_revision.revision_number - 1
        )
        return submitted == current_payload
    return False
