"""Creation-based deadlines; provider verification remains the payment authority."""
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import RegistrationOrder, PaymentAttempt, OrderExpiryPolicy, OrderExpiry, DICAdminAuditEvent

HOURS = 24
IN_FLIGHT = ('initializing', 'pending', 'init_unknown', 'verify_pending')
EXCEPTIONS = ('reconcile', 'amount_mismatch', 'duplicate_success')


def activation():
    return OrderExpiryPolicy.objects.filter(pk=1).values_list('activated_at', flat=True).first()


def deadline(order):
    return order.created_at + timedelta(hours=HOURS)


def protected(order):
    # Recorded paid without trustworthy evidence is also held, never auto-closed.
    return order.registration_basis != 'paid' or order.payment_status in ('paid', 'refunded') or order.payment_attempts.filter(status='successful').exists()


def expired(order, now=None):
    return bool(activation() and not protected(order) and (now or timezone.now()) >= deadline(order))


def metadata(order):
    return dict(enforced=bool(activation()) and not protected(order), expires_at=deadline(order).isoformat(), expired=expired(order), expiry_recorded=OrderExpiry.objects.filter(order=order).exists())


def require_payable(order):
    if expired(order):
        raise ValidationError({'expired': True, 'detail': 'This registration expired after 24 hours. Do not pay again. Contact staff if payment was made.'})


def archive_query(now=None):
    if not activation():
        return Q(pk__in=[])
    return (Q(registration_basis='paid', payment_status__in=('pending', 'failed'),
        created_at__lte=(now or timezone.now()) - timedelta(hours=HOURS))
        & ~Q(payment_attempts__status='successful'))


def evidence_state(order):
    states = set(order.payment_attempts.values_list('status', flat=True))
    if states & set(IN_FLIGHT):
        return 'verification_required'
    if states & set(EXCEPTIONS) or order.payment_status == 'paid':
        return 'reconciliation_required'
    return 'no_success_evidence'


def require_manager(actor):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.can_view_dic_operations')
            and actor.has_perm('dic.can_view_dic_finance')
            and actor.has_perm('dic.manage_dic_order_lifecycle')):
        raise PermissionDenied('Authorized payment lifecycle staff permission is required.')


def audit(actor, action, order=None, **details):
    DICAdminAuditEvent.objects.create(actor=actor, action=action, target_type='RegistrationOrder' if order else 'OrderExpiryPolicy',
        target_id=str(order.public_id) if order else '1', details=details)


@transaction.atomic
def activate(actor):
    require_manager(actor)
    policy, _ = OrderExpiryPolicy.objects.get_or_create(pk=1)
    policy = OrderExpiryPolicy.objects.select_for_update().get(pk=policy.pk)
    if not policy.activated_at:
        policy.activated_at = timezone.now()
        policy.activated_by = actor
        policy.save(update_fields=('activated_at', 'activated_by'))
        audit(actor, 'order_expiry_activated', activated_at=policy.activated_at.isoformat(), hours=HOURS)
    return policy.activated_at


@transaction.atomic
def record_expiry(order_id, actor):
    require_manager(actor)
    order = RegistrationOrder.objects.select_for_update().get(pk=order_id)
    # Same lock order as settlement; an in-flight transaction is retained for
    # verification, never relabelled failed, cancelled or paid by expiration.
    list(PaymentAttempt.objects.select_for_update().filter(order=order).order_by('pk'))
    if not expired(order):
        return False
    row, created = OrderExpiry.objects.get_or_create(order=order,
        defaults=dict(deadline=deadline(order), evidence_state=evidence_state(order)))
    if created:
        audit(actor, 'order_expired', order, deadline=row.deadline.isoformat(), evidence_state=row.evidence_state)
    return created
