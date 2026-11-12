"""Audited late-payment decisions. No charge/refund initiation is performed here."""
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from .models import PaymentAttempt, PaymentResolution, RegistrationOrder
from . import order_lifecycle as lifecycle


def replay(row, actor, reference, request_id, decision, reason, provider_refund_id):
    if row and (row.actor_id != actor.pk or row.attempt.reference != reference or row.decision != decision
            or row.reason != reason or row.provider_refund_id != provider_refund_id):
        raise ValidationError('This decision reference was already used for different details.')
    return row


def resolve(actor, reference, request_id, decision, reason, provider_refund_id=''):
    try:
        return _resolve(actor, reference, request_id, decision, reason, provider_refund_id)
    except IntegrityError:
        # A globally reused request ID can race across different order locks.
        # The losing transaction rolled back completely before this lookup.
        row = PaymentResolution.objects.select_related('attempt').filter(request_id=request_id).first()
        if row is None:
            raise
        return replay(row, actor, reference, request_id, decision, reason, provider_refund_id)


def _resolve(actor, reference, request_id, decision, reason, provider_refund_id=''):
    lifecycle.require_manager(actor)
    existing = PaymentResolution.objects.select_related('attempt').filter(request_id=request_id).first()
    if existing:
        return replay(existing, actor, reference, request_id, decision, reason, provider_refund_id)
    attempt = PaymentAttempt.objects.filter(reference=reference).first()
    if not attempt:
        raise NotFound()
    if not reason.strip() or len(reason) > 1000 or decision not in ('reinstate', 'refund_requested', 'refund_confirmed'):
        raise ValidationError('Choose a decision and record its reason.')
    if decision != 'refund_confirmed' and provider_refund_id:
        raise ValidationError('A provider refund ID belongs only to refund confirmation.')
    from .payments import PaystackClient, PaystackAPIError, PaystackTransportError, PaystackConfigurationError
    from .payment_views import (_apply_verified_transaction, _provider_paid_at, _revision_is_valid_at_payment,
        PaymentProviderUnavailable)
    refund = None
    if decision in ('reinstate', 'refund_confirmed'):
        try:
            client = PaystackClient()
            if decision == 'reinstate':
                _apply_verified_transaction(attempt.pk, client.verify_transaction(reference))
            else:
                if not provider_refund_id.isdigit() or len(provider_refund_id) > 64:
                    raise ValidationError('Enter the Paystack refund ID to verify.')
                refund = client.verify_refund(provider_refund_id)
        except (PaystackAPIError, PaystackTransportError, PaystackConfigurationError):
            raise PaymentProviderUnavailable(reference) from None
    with transaction.atomic():
        order = RegistrationOrder.objects.select_for_update().get(pk=attempt.order_id)
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        existing = PaymentResolution.objects.select_related('attempt').filter(request_id=request_id).first()
        if existing:
            return replay(existing, actor, reference, request_id, decision, reason, provider_refund_id)
        if attempt.resolutions.filter(decision=decision).exists():
            raise ValidationError('This decision is already recorded. Refresh the history.')
        if (order.registration_basis != 'paid' or attempt.provider_mode != settings.PAYSTACK_MODE
                or attempt.failure_code != 'order_expired' or not attempt.provider_transaction_id
                or attempt.provider_status != 'success' or attempt.provider_paid_at is None):
            raise ValidationError('Only independently verified late-payment exceptions can be resolved here.')
        if order.status == 'cancelled' or order.payment_status in ('paid', 'refunded'):
            raise ValidationError('This booking requires separate financial review.')
        if decision == 'reinstate':
            if attempt.resolutions.exists():
                raise ValidationError('A refund decision already exists; do not reinstate this booking.')
            if not _revision_is_valid_at_payment(attempt.price_revision, attempt.provider_paid_at):
                raise ValidationError('The paid quote is not valid. Separate price reconciliation is required.')
            if order.payment_attempts.filter(status__in=('successful', 'duplicate_success')).exclude(pk=attempt.pk).exists():
                raise ValidationError('Another successful charge requires separate reconciliation.')
            attempt.status = 'successful'
            attempt.failure_code = ''
            attempt.save(update_fields=('status', 'failure_code', 'updated_at'))
            order.status, order.payment_status = 'confirmed', 'paid'
            order.current_price_revision = attempt.price_revision
            order.save(update_fields=('status', 'payment_status', 'current_price_revision'))
            order.payment_attempts.filter(status__in=lifecycle.IN_FLIGHT).exclude(pk=attempt.pk).update(
                status='superseded', failure_code='order_paid_by_another_attempt', updated_at=timezone.now())
            from .payment_followups import enqueue_housing
            from .fulfillment import enqueue_verified
            enqueue_housing(order)
            enqueue_verified(order, attempt)
        elif decision == 'refund_confirmed':
            if not attempt.resolutions.filter(decision='refund_requested').exists():
                raise ValidationError('Record the refund decision before confirming its completion.')
            stamp = _provider_paid_at(refund.get('refunded_at'))
            if (refund.get('status') != 'processed' or str(refund.get('id')) != provider_refund_id
                    or str(refund.get('transaction')) != attempt.provider_transaction_id
                    or type(refund.get('amount')) is not int or refund['amount'] != attempt.amount_kobo
                    or refund.get('currency') != attempt.currency or refund.get('domain') != attempt.provider_mode
                    or stamp is None or stamp < attempt.provider_paid_at or stamp > timezone.now()):
                raise ValidationError('A matching provider-confirmed full refund is required. Pending or partial refunds remain under review.')
            order.payment_status = 'refunded'
            order.save(update_fields=('payment_status',))
        row = PaymentResolution.objects.create(attempt=attempt, actor=actor, request_id=request_id,
            decision=decision, reason=reason, provider_refund_id=provider_refund_id)
        lifecycle.audit(actor, 'late_payment_' + decision, order, reference=reference,
            decision_id=str(request_id), reason=reason, provider_refund_id=provider_refund_id)
        return row
