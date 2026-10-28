import re
from uuid import UUID
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from dic.campsite_api import require_campsite_staff
from dic.checkin_services import check_in_participant, checkin_summary, require_checkin_storage
from dic.identity_tokens import digest
from dic.models import CampCheckIn, DigitalIDIssue, Participant, RegistrationOrder, RegistrationOrderItem, DICAdminAuditEvent
from dic.participant_services import eligibility
from .models import Movement


def require(actor, permission):
    require_campsite_staff(actor)
    if not actor.has_perm(permission):
        raise PermissionDenied('This action requires additional staff permission.')


def storage():
    require_checkin_storage()
    if Movement._meta.db_table not in connection.introspection.table_names():
        error = APIException('Movement setup awaits an approved schema application. No presence state is available.')
        error.status_code = 503
        raise error


def resolve_token(token, edition, actor):
    require(actor, 'dic.can_view_dic_ids')
    if not any(actor.has_perm(p) for p in ('dic.can_check_in_dic_participants', 'dic_movement.can_view_movements')):
        raise PermissionDenied('Operational scan permission is required.')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ValidationError('This QR ID is unavailable in the selected edition.')
    issue = DigitalIDIssue.objects.filter(verification_digest=digest(token), revoked_at__isnull=True,
        expires_at__gt=timezone.now(), enrollment__edition=edition).select_related('enrollment__participant').first()
    if not issue or not eligibility(issue.enrollment)['eligible']:
        raise ValidationError('This QR ID is unavailable in the selected edition.')
    return issue.enrollment


def presence(arrived, last_kind):
    if not arrived:
        return 'not_arrived'
    return 'outside' if last_kind == 'departure' else 'inside'


def validate_transition(state, kind):
    if (kind == 'departure' and state != 'inside') or (kind == 'return' and state != 'outside') or kind not in ('departure', 'return'):
        raise ValidationError('Invalid movement transition. Refresh the current presence state.')


def serialize(row):
    return dict(id=str(row.pk), kind=row.kind, time=row.recorded_at.isoformat(),
        staff=row.recorded_by.get_full_name() or row.recorded_by.get_username(), reason=row.reason,
        authorization_reference=row.authorization_reference, sequence=row.sequence)


def snapshot(edition, participant_id, actor):
    # A coherent presence/version/history snapshot, even when a movement commits concurrently.
    rows = list(Movement.objects.filter(edition=edition, participant_id=participant_id).select_related('recorded_by').order_by('sequence'))
    arrival = CampCheckIn.objects.filter(edition=edition, participant_id=participant_id).select_related('checked_in_by').first()
    result = dict(presence=presence(bool(arrival), rows[-1].kind if rows else None),
        version=rows[-1].sequence if rows else 0, check_in=checkin_summary(arrival))
    if actor.has_perm('dic_movement.can_view_movements'):
        result['history'] = [serialize(row) for row in rows]
    return result


def lock_person(edition, participant_id):
    sources = RegistrationOrderItem.objects.filter(order__edition=edition, participant_id=participant_id)
    order_ids = set(sources.values_list('order_id', flat=True))
    if not order_ids:
        raise ValidationError('Participant is not registered in the selected edition.')
    list(RegistrationOrder.objects.select_for_update().filter(pk__in=order_ids).order_by('pk'))
    Participant.objects.select_for_update().get(pk=participant_id)
    if set(sources.values_list('order_id', flat=True)) != order_ids:
        raise ValidationError('Registration changed. Refresh before retrying.')


def departure_authority(actor, data):
    require(actor, 'dic_movement.can_authorize_departure')
    reference = data.get('authorization_reference', '')
    if data.get('authorization_checked') is not True or not isinstance(reference, str) or not reference.strip() or len(reference) > 160:
        raise ValidationError('Confirm the approved release authorization and provide its reference.')
    return reference.strip()


@transaction.atomic
def record_movement(edition, participant_id, actor, data, token=None):
    require(actor, 'dic_movement.can_record_movements')
    require(actor, 'dic_movement.can_view_movements')
    if data.get('confirmed') is not True:
        raise ValidationError('Explicit movement confirmation is required.')
    kind = data.get('action')
    reference = departure_authority(actor, data) if kind == 'departure' else ''
    reason = data.get('reason', '')
    if not isinstance(reason, str) or len(reason) > 1000:
        raise ValidationError('Use a reason of up to 1,000 characters.')
    try:
        request_id = UUID(str(data.get('request_id', '')))
    except ValueError:
        raise ValidationError('A valid request identifier is required.')
    lock_person(edition, participant_id)
    if token is not None:
        subject = resolve_token(token, edition, actor)
        if subject.participant_id != participant_id:
            raise ValidationError('The scanned identity changed.')
    existing = Movement.objects.filter(edition=edition, request_id=request_id).first()
    if existing:
        if (existing.participant_id != participant_id or existing.kind != kind or existing.recorded_by_id != actor.pk
                or existing.reason != reason.strip() or existing.authorization_reference != reference):
            raise ValidationError('This request identifier was already used for a different action.')
        return existing, False
    current = snapshot(edition, participant_id, actor)
    from dic.models import CampEnrollment
    enrollment = CampEnrollment.objects.filter(edition=edition, participant_id=participant_id).first()
    if enrollment and enrollment.source_item.order.registration_basis == 'tutor' and not eligibility(enrollment)['eligible']:
        if kind != 'departure' or current['presence'] != 'inside' or not reason.strip():
            raise ValidationError('Tutor authorization is unavailable. Only a documented staff-authorized departure is allowed.')
    if type(data.get('expected_version')) is not int or data['expected_version'] != current['version']:
        raise ValidationError('Presence changed. Refresh and confirm again.')
    validate_transition(current['presence'], kind)
    row = Movement.objects.create(edition=edition, participant_id=participant_id, kind=kind,
        recorded_by=actor, reason=reason.strip(), authorization_reference=reference,
        sequence=current['version'] + 1, request_id=request_id)
    DICAdminAuditEvent.objects.create(actor=actor, action='camper_' + kind,
        target_type='Movement', target_id=str(row.pk), details=dict(edition=edition.pk,
        participant=str(participant_id), sequence=row.sequence, authorization_reference=reference))
    return row, True


@transaction.atomic
def scan_arrival(edition, token, actor):
    require(actor, 'dic.can_check_in_dic_participants')
    enrollment = resolve_token(token, edition, actor)
    lock_person(edition, enrollment.participant_id)
    # ID issuance/revocation takes the same participant lock; recheck under it.
    enrollment = resolve_token(token, edition, actor)
    return check_in_participant(edition, enrollment.participant_id, actor)
