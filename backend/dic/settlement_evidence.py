"""Settlement evidence only: no participant source-review or refund policy."""
from django.conf import settings


def settlement_reason(attempt, *, allow_refunded=False, timing_check=None):
    order = attempt.order
    if order.registration_basis != 'paid':
        return 'complimentary_registration_not_revenue'
    if order.payment_status == 'refunded' and not allow_refunded:
        return 'refunded'
    if order.status != 'confirmed' or order.payment_status not in (('paid', 'refunded') if allow_refunded else ('paid',)):
        return 'order_not_paid'
    mode = getattr(settings, 'PAYSTACK_MODE', None)
    if (mode not in ('test', 'live') or getattr(attempt, 'provider_mode', None) != mode
            or (getattr(settings, 'SETTINGS_MODULE', '') in ('config.settings.production', 'config.settings.zevcloud') and mode != 'live')):
        return 'provider_mode_review'
    revision = order.current_price_revision
    expected = int(order.total_amount_ngn * 100)
    if (attempt.status != 'successful' or not revision or revision.order_id != order.pk
            or not revision.accepted_at or attempt.price_revision_id != revision.pk
            or attempt.amount_kobo != expected or attempt.currency != 'NGN'
            or attempt.provider_status != 'success' or attempt.provider_reported_amount_kobo != expected
            or attempt.provider_reported_currency != 'NGN' or not attempt.provider_transaction_id
            or not attempt.verified_at or not attempt.provider_paid_at):
        return 'unverified_evidence'
    if timing_check is None:
        from .payment_views import _revision_is_valid_at_payment
        timing_check = _revision_is_valid_at_payment
    return '' if timing_check(revision, attempt.provider_paid_at) else 'unverified_evidence'


def order_has_verified_settlement(order):
    # Preserve all history. A conflicting attempt blocks new allocation rather
    # than being silently ignored in favour of a successful receipt.
    attempts = list(order.payment_attempts.select_related('order__current_price_revision', 'price_revision'))
    if any(row.status in ('reconcile', 'amount_mismatch', 'duplicate_success') for row in attempts):
        return False
    return any(not settlement_reason(row) for row in attempts)
