"""Simple combined house leaderboard and accountable, append-only corrections."""
import re
from django.db import connection, transaction
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from .campsite_api import require_campsite_staff
from .models import CampEdition, House, HouseScoreTransaction, DICAdminAuditEvent


def require_scoring_staff(user, permission='can_view_dic_scores'):
    require_campsite_staff(user)
    if not user.has_perm('dic.can_view_dic_scores') or not user.has_perm(f'dic.{permission}'):
        raise PermissionDenied('Your account does not have the required House Scoring permission.')


def require_scoring_storage():
    if HouseScoreTransaction._meta.db_table not in connection.introspection.table_names():
        error = APIException('House Scoring setup is pending. Ask your administrator to review the proposed database migration.')
        error.status_code = 503
        raise error


def scoring_houses(edition):
    # Include both genders and zero-point houses. Never manufacture eight records.
    return House.objects.filter(edition=edition, purpose='participants').order_by('name', 'pk')


def combined_leaderboard(houses, entries):
    scores = {house.pk: dict(house_id=house.pk, name=house.name, gender=house.gender,
        colour=house.badge_colour if re.fullmatch(r'#[0-9a-fA-F]{6}', house.badge_colour or '') else None,
        awarded=0, deducted=0, net=0) for house in houses}
    for entry in entries:
        if entry.house_id not in scores:
            continue
        row = scores[entry.house_id]
        row['awarded' if entry.entry_type == 'award' else 'deducted'] += entry.points
    for row in scores.values():
        row['net'] = row['awarded'] - row['deducted']
    rows = sorted(scores.values(), key=lambda row: (-row['net'], row['name'].casefold(), row['house_id']))
    previous, rank = None, 0
    for index, row in enumerate(rows, 1):
        if row['net'] != previous:
            rank = index
        row['rank'] = rank
        previous = row['net']
    return rows


def scoring_history_row(row):
    return dict(id=row.pk, house_id=row.house_id, house=row.house.name,
        activity=row.activity, entry_type=row.entry_type, points=row.points, note=row.note,
        staff=row.created_by.get_full_name() or row.created_by.get_username(),
        time=row.created_at.isoformat(), reverses=row.reverses_id,
        reversed_by=getattr(getattr(row, 'reversal', None), 'pk', None))


def repeat_or_conflict(existing, values):
    if existing:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise ValidationError('This submission reference was already used for different details. Refresh and try again.')
        return existing, False
    return None


def append_score(edition, actor, request_id, values):
    existing = HouseScoreTransaction.objects.filter(edition=edition, request_id=request_id).first()
    repeated = repeat_or_conflict(existing, values)
    if repeated:
        return repeated
    row = HouseScoreTransaction.objects.create(edition=edition, created_by=actor, request_id=request_id, **values)
    DICAdminAuditEvent.objects.create(actor=actor, action='house_score_reversed' if values['reverses_id'] else 'house_score_recorded',
        target_type='HouseScoreTransaction', target_id=str(row.pk),
        details=dict(edition=edition.pk, house=values['house_id'], points=values['points'],
            entry_type=values['entry_type'], reverses=values['reverses_id']))
    return row, True


@transaction.atomic
def record_score(edition, actor, data):
    require_scoring_staff(actor, 'can_record_dic_scores')
    from .scoring_catalogue import catalogue
    reserved = {value.casefold() for rule in catalogue() for value in (rule.code, rule.name)}
    if data['entry_type'] == 'award' and data['activity'].strip().casefold() in reserved:
        raise ValidationError('Use the approved activity selector for catalogue awards. Direct house awards are for other agreed adjustments.')
    # Serialise this small camp's writes, including idempotency checks/corrections.
    CampEdition.objects.select_for_update().get(pk=edition.pk)
    house = scoring_houses(edition).filter(pk=data['house']).first()
    if not house:
        raise ValidationError('Choose a participant house belonging to this camp edition.')
    values = dict(house_id=house.pk, entry_type=data['entry_type'], points=data['points'],
        activity=data['activity'], note=data.get('note', ''), reverses_id=None)
    return append_score(edition, actor, data['request_id'], values)


@transaction.atomic
def reverse_score(edition, actor, entry_id, data):
    require_scoring_staff(actor, 'can_correct_dic_scores')
    CampEdition.objects.select_for_update().get(pk=edition.pk)
    original = HouseScoreTransaction.objects.filter(edition=edition, pk=entry_id).first()
    if not original or original.reverses_id:
        raise ValidationError('Choose an original scoring entry in this camp edition.')
    values = dict(house_id=original.house_id, entry_type='deduction' if original.entry_type == 'award' else 'award',
        points=original.points, activity=original.activity, note=data['reason'], reverses_id=original.pk)
    repeated = repeat_or_conflict(HouseScoreTransaction.objects.filter(edition=edition, request_id=data['request_id']).first(), values)
    if repeated:
        return repeated
    if HouseScoreTransaction.objects.filter(reverses=original).exists():
        raise ValidationError('This entry was already reversed. Refresh the history.')
    from .scoring_catalogue import INDIVIDUAL_ACTIVITIES
    if original.activity in {row.name for row in INDIVIDUAL_ACTIVITIES}:
        from .activity_scoring import check_reversal_dependencies
        check_reversal_dependencies(original)
    return append_score(edition, actor, data['request_id'], values)
