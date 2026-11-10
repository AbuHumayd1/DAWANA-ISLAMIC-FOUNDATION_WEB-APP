"""Durable ID-only outbox; the current HousingJob pipeline exclusively owns housing.

Disabled by default. Payment settlement only enqueues; workers process later.
No redirect, portal read, or UI rendering can issue a credential.
"""
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.db import connection, transaction, OperationalError, InterfaceError
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied as PortalPermissionDenied

from .models import (CamperFulfillmentJob, RegistrationOrder, RegistrationOrderItem,
    CampEdition, DigitalIDIssue, DICAdminAuditEvent)
from .participant_services import ensure_enrollment, eligibility, require_id_manager, id_command

class FulfillmentHold(Exception):
    def __init__(self, code):
        self.code = code


def enabled():
    return getattr(settings, 'DIC_AUTO_FULFILLMENT_ENABLED', False) is True


def portal_status(order):
    if not enabled():
        return None
    state = CamperFulfillmentJob.objects.filter(order=order).values_list('state', flat=True).first()
    messages = {'pending': 'Your Digital ID is being prepared.',
        'processing': 'Your Digital ID is being prepared.',
        'held': 'The DIC team needs to review your Digital ID preparation.',
        'failed': 'Digital ID preparation is pending a controlled retry.',
        'completed': 'Digital ID preparation is complete.'}
    return {'state': state, 'message': messages[state]} if state in messages else None


def audit(job, action, actor=None, **details):
    DICAdminAuditEvent.objects.create(actor=actor, action='camper_fulfillment_' + action,
        target_type='CamperFulfillmentJob', target_id=str(job.pk),
        details={'state': job.state, 'reason_code': job.reason_code, 'attempts': job.attempts, **details})


def authority():
    actor_id = getattr(settings, 'DIC_AUTO_FULFILLMENT_ACTOR_ID', 0)
    if type(actor_id) is not int or not 0 < actor_id <= 2**63 - 1:
        raise FulfillmentHold('automation_authority_unconfigured')
    actor = get_user_model().objects.filter(pk=actor_id).first()
    try:
        require_id_manager(actor)
    except (PermissionDenied, PortalPermissionDenied):
        raise FulfillmentHold('automation_authority_unavailable') from None
    return actor


def enqueue_verified(order, attempt):
    """Durable ID outbox in the trusted settlement transaction; no housing DDL."""
    if not enabled():
        return None
    if (order.registration_basis != 'paid' or order.status != 'confirmed'
            or order.payment_status != 'paid' or attempt.order_id != order.pk
            or attempt.status != 'successful' or attempt.provider_status != 'success'
            or not attempt.verified_at or not attempt.provider_paid_at
            or not attempt.provider_transaction_id):
        return None
    from .settlement_evidence import order_has_verified_settlement, settlement_reason
    if settlement_reason(attempt) or not order_has_verified_settlement(order):
        return None
    job, created = CamperFulfillmentJob.objects.get_or_create(order=order)
    if created:
        audit(job, 'enqueued')
    return job.pk


def dispatch(job_id):
    """Explicit ID dispatch; payment itself never executes fulfillment."""
    if enabled():
        return process(job_id)


def _group_items(order, *, lock=True):
    # ID scope is the actual checkout participants, not housing guardians/dependents
    # on other orders. Each paid order has its own independent ID outbox.
    items = list(order.items.select_related('participant', 'order__edition').order_by('participant_id', 'pk'))
    if not items:
        raise FulfillmentHold('empty_registration')
    member_ids = {item.participant_id for item in items}
    order_ids = sorted(set(RegistrationOrderItem.objects.filter(participant_id__in=member_ids,
        order__edition_id=order.edition_id).values_list('order_id', flat=True)) | {order.pk})
    if lock:
        list(RegistrationOrder.objects.select_for_update().filter(pk__in=order_ids).order_by('pk'))
    return items, member_ids, order_ids


def _issue_item(item, actor):
    enrollment = ensure_enrollment(item.pk)
    if not eligibility(enrollment)['eligible']:
        raise FulfillmentHold('registration_eligibility_review_required')
    previous = list(DigitalIDIssue.objects.filter(enrollment=enrollment))
    if previous:
        current = [issue for issue in previous if not issue.revoked_at and issue.expires_at > timezone.now()]
        if len(current) != 1 or not current[0].verification_digest or not current[0].verification_secret:
            raise FulfillmentHold('existing_id_requires_review')
        from .identity_tokens import read_token, digest
        try:
            matches = secrets.compare_digest(current[0].verification_digest, digest(read_token(current[0])))
        except Exception:
            raise FulfillmentHold('existing_id_requires_review') from None
        if not matches:
            raise FulfillmentHold('existing_id_requires_review')
    # No housing or check-in prerequisite is added to the original ID contract.
    id_command(enrollment.pk, 'issue', actor=actor,
               reason='Automatic first issuance after verified payment.')


def _complete(job, actor, items, member_ids):
    order = RegistrationOrder.objects.get(pk=job.order_id)
    from .settlement_evidence import order_has_verified_settlement
    if (order.registration_basis != 'paid' or order.status != 'confirmed'
            or order.payment_status != 'paid' or not order_has_verified_settlement(order)):
        raise FulfillmentHold('registration_not_verified_paid')
    failures = []
    for item in items:
        try:
            with transaction.atomic():
                _issue_item(item, actor)
        except FulfillmentHold as error:
            failures.append(('held', error.code))
        except (DjangoValidationError, ValidationError, PermissionDenied, PortalPermissionDenied):
            failures.append(('held', 'issuance_review_required'))
        except (OperationalError, InterfaceError):
            failures.append(('pending', 'temporary_database_failure'))
        except Exception:
            failures.append(('failed', 'processing_error'))
        else:
            audit(job, 'item_completed', actor, registration_item=item.pk)
            continue
        audit(job, 'item_' + failures[-1][0], actor,
              registration_item=item.pk, item_reason=failures[-1][1])
    # Successful siblings remain issued. Retry preserves their current credentials.
    return next((failure for failure in failures if failure[0] == 'pending'),
                next((failure for failure in failures if failure[0] == 'failed'),
                failures[0] if failures else ('completed', '')))


def process(job_id):
    """ID-only work. Never claims or changes a HousingJob or HouseAllocation."""
    if not enabled():
        return 'disabled'
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '30s'")
        reference = CamperFulfillmentJob.objects.select_related('order').get(pk=job_id)
        if reference.state != 'pending' or (reference.retry_at and reference.retry_at > timezone.now()):
            return reference.state
        discovery_error = None
        try:
            items, member_ids, order_ids = _group_items(reference.order)
        except FulfillmentHold as error:
            discovery_error = error
        CampEdition.objects.select_for_update().get(pk=reference.order.edition_id)
        job = CamperFulfillmentJob.objects.select_for_update().get(pk=job_id)
        if job.state != 'pending' or (job.retry_at and job.retry_at > timezone.now()):
            return job.state
        actor = None
        job.state, job.reason_code = 'processing', ''
        job.attempts += 1
        job.save(update_fields=['state', 'attempts', 'reason_code', 'updated_at'])
        audit(job, 'started')
        try:
            actor = authority()
            if discovery_error is not None:
                raise discovery_error
            current_items, current_members, current_orders = _group_items(reference.order, lock=False)
            if (current_members != member_ids or current_orders != order_ids
                    or [item.pk for item in current_items] != [item.pk for item in items]):
                raise FulfillmentHold('registration_group_changed')
            job.state, job.reason_code = _complete(job, actor, items, member_ids)
        except FulfillmentHold as error:
            job.state, job.reason_code = 'held', error.code
        except (DjangoValidationError, ValidationError, PermissionDenied, PortalPermissionDenied):
            job.state, job.reason_code = 'held', 'issuance_review_required'
        # Unexpected infrastructure errors roll back the job to durable pending;
        # no partial processing claim is committed and no payment is rolled back.
        if job.state == 'pending':
            job.state = 'pending' if job.attempts < 5 else 'failed'
            job.retry_at = timezone.now() + timedelta(seconds=min(60 * 2 ** min(job.attempts, 6), 3600))
        else:
            job.retry_at = None
        job.processed_by = actor
        job.save(update_fields=['state', 'reason_code', 'processed_by', 'retry_at', 'updated_at'])
        audit(job, job.state, actor)
        return job.state


@transaction.atomic
def retry(job_id, actor):
    """Explicit ID retry only; it does not release a housing hold."""
    if not enabled():
        raise ValidationError('Fulfillment automation is disabled.')
    require_id_manager(actor)
    reference = CamperFulfillmentJob.objects.select_related('order').get(pk=job_id)
    CampEdition.objects.select_for_update().get(pk=reference.order.edition_id)
    job = CamperFulfillmentJob.objects.select_for_update().get(pk=job_id)
    if job.state not in ('held', 'failed'):
        raise ValidationError('Only held or failed ID jobs can be explicitly retried.')
    job.state, job.reason_code, job.retry_at = 'pending', '', None
    job.save(update_fields=['state', 'reason_code', 'retry_at', 'updated_at'])
    audit(job, 'retry_authorized', actor)
    transaction.on_commit(lambda: dispatch(job.pk))
    return job
