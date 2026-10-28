"""Physical arrival only. Never prepare IDs or change registrations/payments."""
from types import SimpleNamespace
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from .campsite_api import require_campsite_staff
from .models import (CampCheckIn, CampEnrollment, Participant, RegistrationOrder,
    RegistrationOrderItem, HouseAllocation, DICAdminAuditEvent)
from .participant_services import eligibility


REASONS = {
    'authorized_tutor': 'Authorized complimentary tutor',
    'tutor_authorization_required': 'Tutor authorization unavailable or revoked',
    'verified_paid': 'Verified and eligible',
    'registration_not_verified_paid': 'Registration or payment is not verified',
    'source_review_required': 'Registration sources need review',
    'restricted_review_required': 'Participant record needs staff review',
    'invalid_source': 'Registration source needs review',
    'settlement_evidence_review_required': 'Payment evidence needs review',
    'reconciliation_review_required': 'Payment reconciliation needs review',
}


def require_checkin_staff(user):
    require_campsite_staff(user)
    if not user.has_perm('dic.can_check_in_dic_participants'):
        raise PermissionDenied('Your account does not have Camp Check-in permission.')


def require_checkin_storage():
    # Deployment can safely precede the explicitly approved schema change.
    if CampCheckIn._meta.db_table not in connection.introspection.table_names():
        error = APIException('Camp Check-in setup is pending. Ask your administrator to review the proposed database migration.')
        error.status_code = 503
        raise error


def candidate_for(item, enrollment=None):
    return enrollment or SimpleNamespace(source_item_id=item.pk,
        participant_id=item.participant_id, edition_id=item.order.edition_id,
        source_review_fingerprint='', restriction_reason='')


def checkin_summary(row):
    if row is None:
        return None
    return dict(time=row.checked_in_at.isoformat(),
        staff=row.checked_in_by.get_full_name() or row.checked_in_by.get_username())


def checkin_directory(edition, search=''):
    """Small camp directory. Totals always describe the entire selected edition."""
    items = RegistrationOrderItem.objects.filter(order__edition=edition).select_related(
        'participant', 'order', 'category').order_by('participant__full_name', 'participant_id', 'pk')
    enrollments = {row.participant_id: row for row in CampEnrollment.objects.filter(edition=edition)}
    arrivals = {row.participant_id: row for row in CampCheckIn.objects.filter(edition=edition).select_related('checked_in_by')}
    houses = {row.participant_id: row.house.name for row in HouseAllocation.objects.filter(
        edition=edition, status='allocated').select_related('house')}
    seen, rows, needs_attention = set(), [], 0
    checked_in = 0
    for item in items:
        if item.participant_id in seen:
            continue
        seen.add(item.participant_id)
        enrollment = enrollments.get(item.participant_id)
        # Display the same source used by the established eligibility service.
        if enrollment:
            item = RegistrationOrderItem.objects.select_related('participant', 'order', 'category').filter(
                pk=enrollment.source_item_id, participant_id=item.participant_id, order__edition=edition).first() or item
        result = eligibility(candidate_for(item, enrollment))
        arrival = arrivals.get(item.participant_id)
        checked_in += int(arrival is not None)
        needs_attention += int(not result['eligible'])
        number = enrollment.participant_number if enrollment else str(item.order.public_id)
        row = dict(participant_id=str(item.participant_id), name=item.participant.full_name,
            registration_number=str(item.order.public_id), participant_number=number,
            registration_status=item.order.status,
            payment_status=item.order.payment_status, registration_basis=item.order.registration_basis,
            eligibility=dict(**result, label=REASONS.get(result['code'], 'Staff review required')),
            house=houses.get(item.participant_id), check_in=checkin_summary(arrival))
        terms = (row['name'], number, row['registration_number'], str(item.order_id))
        if not search or any(search.casefold() in value.casefold() for value in terms):
            rows.append(row)
    return rows, dict(registered=len(seen), checked_in=checked_in,
        not_yet_arrived=len(seen)-checked_in, needs_attention=needs_attention)


@transaction.atomic
def check_in_participant(edition, participant_id, actor):
    require_checkin_staff(actor)
    # Same order-before-participant lock order as issuance/settlement; eligibility
    # is rechecked here, regardless of what the browser last displayed.
    sources = RegistrationOrderItem.objects.filter(participant_id=participant_id, order__edition=edition)
    order_ids = set(sources.values_list('order_id', flat=True))
    if not order_ids:
        raise ValidationError('Participant is not registered for this camp edition.')
    list(RegistrationOrder.objects.select_for_update().filter(pk__in=order_ids).order_by('pk'))
    Participant.objects.select_for_update().get(pk=participant_id)
    if set(sources.values_list('order_id', flat=True)) != order_ids:
        raise ValidationError('Registration changed. Refresh and try again.')
    existing = CampCheckIn.objects.filter(edition=edition, participant_id=participant_id).select_related('checked_in_by').first()
    if existing:
        return existing, False  # Preserve the original arrival time and staff.
    enrollment = CampEnrollment.objects.select_for_update().filter(edition=edition, participant_id=participant_id).first()
    item = sources.select_related('order', 'category').order_by('pk').first()
    result = eligibility(candidate_for(item, enrollment))
    if not result['eligible']:
        raise ValidationError(REASONS.get(result['code'], 'Staff review required'))
    row, created = CampCheckIn.objects.get_or_create(edition=edition, participant_id=participant_id,
        defaults=dict(checked_in_at=timezone.now(), checked_in_by=actor))
    if created:
        DICAdminAuditEvent.objects.create(actor=actor, action='participant_checked_in',
            target_type='CampCheckIn', target_id=str(row.pk),
            details=dict(edition=edition.pk, participant=str(participant_id)))
    return row, created
