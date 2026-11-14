"""Audited registration trash, restoration and separate archival; retain financial history."""
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
    if is_deleted(order):
        raise ValidationError('This registration is in Trash; use Restore from Trash.')
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


def disposable_permission(actor):
    return (actor.is_authenticated and actor.is_active and actor.is_staff
        and actor.has_perm('dic.delete_registrationorder')
        and actor.has_perm('dic.can_manage_registration_access'))


def deletion_event(order):
    return DICAdminAuditEvent.objects.filter(target_type='RegistrationOrder', target_id=str(order.pk),
        action__in=('registration_trashed', 'registration_restored')).order_by('-pk').first()


def is_deleted(order):
    event = deletion_event(order)
    return bool(event and event.action == 'registration_trashed')


def deleted_orders():
    from django.db.models import OuterRef, Subquery, CharField
    from django.db.models.functions import Cast
    latest = DICAdminAuditEvent.objects.filter(target_type='RegistrationOrder',
        target_id=Cast(OuterRef('pk'), CharField()), action__in=('registration_trashed', 'registration_restored')).order_by('-pk').values('action')[:1]
    return RegistrationOrder.objects.annotate(_deletion_state=Subquery(latest)).filter(_deletion_state='registration_trashed')


def disposal_blocker(order):
    blocker = archive_blocker(order, allow_deleted=True)
    if blocker:
        return blocker
    state = payment_cleanup_state(order)
    if state not in ('no_payment_attempt', 'failed_evidence_retained'):
        return 'Payment is unresolved or mismatched. Verify/reconcile it before deletion; a failed label alone is insufficient.'
    for attempt in order.payment_attempts.all():
        if attempt.provider_paid_at or attempt.provider_status == 'success' or attempt.resolutions.exists():
            return 'Payment or resolution evidence requires finance review before deletion.'
    return ''


def _activity(actor, action, order, reason, outcome='success', **details):
    return DICAdminAuditEvent.objects.create(actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action, target_type='RegistrationOrder', target_id=str(order.pk),
        details={'reference': str(order.public_id), 'actor_id': actor.pk, 'actor_username': actor.get_username(),
            'reason': reason.strip()[:1000], 'outcome': outcome, **details})


def _change_trash(public_id, actor, confirmation, reason, restore=False):
    action = 'registration_restored' if restore else 'registration_trashed'
    try:
        return _change_trash_locked(public_id, actor, confirmation, reason, restore)
    except (ValidationError, PermissionDenied, RegistrationOrder.DoesNotExist) as error:
        # The failed mutation's transaction has rolled back. Keep its outcome.
        if getattr(actor, 'is_authenticated', False):
            DICAdminAuditEvent.objects.create(actor=actor, action=action+'_rejected',
                target_type='RegistrationOrder', target_id=str(public_id),
                details={'reference': str(public_id), 'actor_id': actor.pk, 'actor_username': actor.get_username(),
                    'outcome': 'rejected', 'reason': str(error)[:1000]})
        raise


@transaction.atomic
def _change_trash_locked(public_id, actor, confirmation, reason, restore):
    if not disposable_permission(actor):
        raise PermissionDenied('Registration deletion and management permissions are required.')
    order = RegistrationOrder.objects.select_for_update().get(public_id=public_id)
    if confirmation != str(order.public_id) or not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Confirm the exact registration reference and give a reason.')
    list(order.payment_attempts.select_for_update().order_by('pk'))
    list(CampEnrollment.objects.select_for_update().filter(source_item__order=order))
    deleted = is_deleted(order)
    if restore:
        if not deleted:
            raise ValidationError('This registration is not in Trash.')
        blocker = disposal_blocker(order)
        if blocker:
            raise ValidationError('Restoration requires review: '+blocker)
        from .security import new_order_access_token, digest_value
        order.access_token_digest = digest_value(new_order_access_token())
        order.access_token_expires_at = timezone.now()
        order.access_token_revoked_at = None
        order.save(update_fields=['access_token_digest', 'access_token_expires_at', 'access_token_revoked_at'])
        _activity(actor, 'registration_restored', order, reason)
    else:
        if deleted:
            _activity(actor, 'registration_trash_repeat', order, reason, outcome='already_deleted')
            return str(order.public_id)
        blocker = disposal_blocker(order)
        if blocker:
            raise ValidationError(blocker)
        order.access_token_revoked_at = timezone.now()
        order.save(update_fields=['access_token_revoked_at'])
        _activity(actor, 'registration_trashed', order, reason,
            payment_state=payment_cleanup_state(order),
            transaction_references=list(order.payment_attempts.values_list('reference', flat=True)))
    return str(order.public_id)


def delete_disposable_registration(public_id, actor, confirmation, reason):
    """Reversible deletion. No order, transaction, participant or audit row is purged."""
    return _change_trash(public_id, actor, confirmation, reason)


def restore_deleted_registration(public_id, actor, confirmation, reason):
    return _change_trash(public_id, actor, confirmation, reason, restore=True)


def payment_cleanup_state(order):
    from django.conf import settings
    attempts = list(order.payment_attempts.all())
    if order.payment_status in ('paid', 'refunded') or any(a.status in ('successful', 'duplicate_success') for a in attempts):
        return 'successful_or_protected'
    if not attempts:
        return 'no_payment_attempt'
    def closed_failure(a):
        rejected = (a.status == 'failed' and a.failure_code == 'provider_rejected_initialization'
            and not a.authorization_url and not a.provider_transaction_id and a.verified_at is None)
        verified = (a.status == 'failed' and a.provider_status == 'failed' and a.verified_at is not None
            and bool(a.provider_transaction_id) and not a.failure_code and a.provider_paid_at is None
            and a.provider_mode == settings.PAYSTACK_MODE and a.currency == a.provider_reported_currency == 'NGN'
            and a.provider_reported_amount_kobo == a.amount_kobo)
        return rejected or verified
    if all(closed_failure(a) for a in attempts):
        return 'failed_evidence_retained'
    if any(a.status in ('amount_mismatch', 'reconcile') or a.failure_code.startswith('provider_data_') for a in attempts):
        return 'reconciliation_required'
    return 'payment_in_progress_or_unknown'


def archive_blocker(order, allow_deleted=False):
    if not allow_deleted and is_deleted(order):
        return 'Restore this registration from Trash before archiving it.'
    from .models import HouseAllocation
    if order.registration_basis != 'paid' or order.payment_status not in ('pending', 'failed') or order.status == 'confirmed':
        return 'Paid, refunded and complimentary registrations cannot use test archival.'
    if order.payment_attempts.filter(status__in=('successful', 'duplicate_success')).exists():
        return 'Successful payment evidence protects this registration.'
    ids = order.items.values_list('participant_id', flat=True)
    if (CampCheckIn.objects.filter(edition=order.edition, participant_id__in=ids).exists()
            or HouseAllocation.objects.filter(edition=order.edition, participant_id__in=ids).exists()
            or CampEnrollment.objects.filter(edition=order.edition, participant_id__in=ids, id_issues__isnull=False).exists()):
        return 'An issued ID, check-in or housing record protects this registration.'
    return ''


def archived_test_orders():
    from django.db.models import OuterRef, Subquery, CharField
    from django.db.models.functions import Cast
    latest = DICAdminAuditEvent.objects.filter(target_type='RegistrationOrder', target_id=Cast(OuterRef('pk'), CharField()),
        action__in=('registration_test_archived', 'registration_restored')).order_by('-pk').values('action')[:1]
    return RegistrationOrder.objects.annotate(_archive_state=Subquery(latest)).filter(
        _archive_state='registration_test_archived', payment_status__in=('pending', 'failed'),
        registration_basis='paid').exclude(status='confirmed')


@transaction.atomic
def archive_test_registration(public_id, actor, confirmation, reason):
    if not disposable_permission(actor):
        raise PermissionDenied('Registration deletion and management permissions are required.')
    order = RegistrationOrder.objects.select_for_update().get(public_id=public_id)
    if confirmation != str(order.public_id) or not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Confirm the registration reference and give a test-record archival reason.')
    blocker = archive_blocker(order)
    if blocker:
        raise ValidationError(blocker)
    if not archived_test_orders().filter(pk=order.pk).exists():
        DICAdminAuditEvent.objects.create(actor=actor, action='registration_test_archived',
            target_type='RegistrationOrder', target_id=str(order.pk), details={'reference': str(order.public_id),
                'reason': reason.strip()[:1000], 'payment_state': payment_cleanup_state(order), 'outcome': 'success',
                'actor_id': actor.pk, 'actor_username': actor.get_username()})
    # No payment state, token, attempt, account or registration is deleted/cancelled.
    # A later verified settlement returns the order to active lists automatically.
    return str(order.public_id)
