"""Synthetic database fixtures only; never imported by application services."""
from django.conf import settings
from django.utils import timezone
from .models import RegistrationOrderPriceRevision, RegistrationOrderPriceItem


def complete_settlement_fixture(order, attempt):
    items = list(order.items.all())
    total = sum(item.fee_snapshot_ngn for item in items)
    revision = RegistrationOrderPriceRevision.objects.create(order=order, revision_number=1,
        total_amount_ngn=total, accepted_at=timezone.now())
    for item in items:
        RegistrationOrderPriceItem.objects.create(revision=revision, order_item=item,
            category_name_snapshot=item.category_name_snapshot,
            regular_fee_snapshot_ngn=item.fee_snapshot_ngn,
            fee_snapshot_ngn=item.fee_snapshot_ngn, price_type='regular')
    order.current_price_revision = revision
    order.save(update_fields=['current_price_revision'])
    attempt.price_revision = revision
    attempt.provider_mode = settings.PAYSTACK_MODE
    attempt.provider_status = 'success'
    attempt.provider_transaction_id = 'fixture-' + str(attempt.pk)
    attempt.provider_reported_amount_kobo = int(total * 100)
    attempt.provider_reported_currency = 'NGN'
    attempt.provider_paid_at = timezone.now()
    attempt.verified_at = timezone.now()
    attempt.save()
