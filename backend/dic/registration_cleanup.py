"""Reversible, individual cancellation; never deletes history or settles money."""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import RegistrationOrder, CampEnrollment, CampCheckIn, DICAdminAuditEvent


@transaction.atomic
def review_registration(order_id, actor, action, reason):
    if not (actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.change_registrationorder')
            and actor.has_perm('dic.can_manage_registration_access')):
        raise PermissionDenied('Registration management permission is required.')
    if action not in ('cancel', 'restore') or not reason.strip():
        raise ValidationError('Choose an action and provide a reason.')
    order = RegistrationOrder.objects.select_for_update().get(pk=order_id)
    # Lock order first, matching payment initialization/settlement lock order.
    # Even failed attempts are retained for reconciliation, never auto-disposed.
    if (order.registration_basis != 'paid' or order.payment_status not in ('pending', 'failed')
            or order.payment_attempts.exists()):
        raise ValidationError('Bookings with payments or payment attempts require reconciliation and cannot use this action.')
    participant_ids = order.items.values_list('participant_id', flat=True)
    if (CampEnrollment.objects.filter(edition=order.edition, participant_id__in=participant_ids, id_issues__isnull=False).exists()
            or CampCheckIn.objects.filter(edition=order.edition, participant_id__in=participant_ids).exists()):
        raise ValidationError('Issued IDs or checked-in participants require staff review; this booking cannot be cancelled here.')
    if action == 'cancel':
        if order.status != 'submitted':
            raise ValidationError('Only an unpaid submitted booking can be cancelled.')
        order.status = 'cancelled'
        order.access_token_revoked_at = timezone.now()
        fields = ['status', 'access_token_revoked_at']
    else:
        if order.status != 'cancelled' or not DICAdminAuditEvent.objects.filter(
                action='registration_cleanup_cancel', target_type='RegistrationOrder', target_id=str(order.pk)).exists():
            raise ValidationError('Only bookings cancelled through this reviewed action can be restored.')
        order.status = 'submitted'
        # Replace, rather than revive, old bearer credentials. Clear the
        # revocation only so verified booking recovery can issue a fresh token.
        from .security import new_order_access_token, digest_value
        order.access_token_digest = digest_value(new_order_access_token())
        order.access_token_expires_at = timezone.now()
        order.access_token_revoked_at = None
        fields = ['status', 'access_token_digest', 'access_token_expires_at', 'access_token_revoked_at']
    order.save(update_fields=fields)
    DICAdminAuditEvent.objects.create(actor=actor, action='registration_cleanup_' + action,
        target_type='RegistrationOrder', target_id=str(order.pk), details={'reason': reason.strip()[:1000]})
    return order
