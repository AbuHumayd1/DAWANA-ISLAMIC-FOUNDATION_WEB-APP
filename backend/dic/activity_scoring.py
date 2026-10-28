"""Small fixed-policy activity layer; house totals stay in the existing ledger."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from dic_scoring.models import ActivityAward
from .models import (CampEdition, Participant, CampEnrollment, RegistrationOrder,
    RegistrationOrderItem, HouseAllocation, CampCheckIn, HouseScoreTransaction, LAGOS_TIME_ZONE)
from .participant_services import eligibility
from .scoring_catalogue import PRAYERS, RAWATIB, activity_for
from .scoring_services import require_scoring_staff, append_score, scoring_houses


def activity_storage_ready():
    return ActivityAward._meta.db_table in connection.introspection.table_names()


def require_activity_storage():
    if not activity_storage_ready():
        error = APIException('Activity scoring schema is pending. Existing house scoring remains available.')
        error.status_code = 503
        raise error


def award_keys(rule, day, slot):
    if rule.frequency == 'prayer' and slot not in PRAYERS:
        raise ValidationError('Select one of the five obligatory prayers.')
    if rule.frequency == 'rawatib' and slot not in RAWATIB:
        raise ValidationError('Select an approved Rawātib prayer period.')
    if rule.frequency in ('session', 'target') and not slot:
        raise ValidationError('Enter the approved target, task, incident or session reference; reuse it for the same achievement.')
    if rule.frequency not in ('prayer', 'rawatib', 'session', 'target') and slot:
        raise ValidationError('This activity does not use a prayer or session reference.')
    period = 'edition' if rule.frequency == 'once' else day.isoformat()
    if rule.frequency in ('prayer', 'rawatib'):
        period += ':' + slot
    elif rule.frequency in ('target', 'session'):
        period = slot  # Approved identifiers are unique throughout this edition.
    return f'{rule.code}:{period}', f'{rule.exclusion_group}:{period}' if rule.exclusion_group else ''


def cap_check(bucket, used, points):
    if bucket and used + points > 10:
        raise ValidationError(f'The separate daily {bucket} allowance is 10 points; {used} already awarded. No partial award was saved.')


def collective_points(rule, eligible_ids, exemptions, attendees):
    eligible_ids, attendees = set(eligible_ids), list(attendees)
    excluded = {row['participant'] for row in exemptions}
    if len(excluded) != len(exemptions) or not excluded <= eligible_ids:
        raise ValidationError('Exemptions must identify distinct eligible house members.')
    if any(not row['reason'].strip() for row in exemptions):
        raise ValidationError('Every approved exemption needs a documented reason.')
    if len(attendees) != len(set(attendees)) or not set(attendees) <= eligible_ids - excluded:
        raise ValidationError('Participants must be distinct eligible, non-exempt house members.')
    denominator = len(eligible_ids - excluded)
    numerator = len(attendees)
    if rule.mode in ('participation', 'prayer_target'):
        if denominator == 0:
            raise ValidationError('No eligible non-exempt members; no participation bonus can be awarded.')
        if Decimal(numerator * 100) < Decimal(rule.threshold) * denominator:
            raise ValidationError('The approved participation threshold was not reached. No points were posted.')
        points = rule.points
    else:
        points = rule.points
    return points, dict(numerator=numerator, denominator=denominator,
        percentage=str(Decimal(numerator * 100) / denominator) if denominator else None)


def milestone_sources(code, rows, reading_target=''):
    """Return verified underlying ledger IDs, or reject an unearned milestone."""
    by_code = {}
    for row in rows:
        by_code.setdefault(row.activity_code, []).append(row)
    required = {'MIL01': ('SAL06',), 'MIL02': ('ADH01', 'ADH02'), 'MIL03': ('QUR01',)}
    selected = []
    if code in required:
        groups = [by_code.get(activity, []) for activity in required[code]]
        days = set.intersection(*({row.activity_date for row in group} for group in groups))
        start = next((day for day in sorted(days) if all(day + timedelta(days=i) in days for i in range(3))), None)
        if start:
            selected = [row for group in groups for row in group if start <= row.activity_date <= start + timedelta(days=2)]
    elif code == 'MIL04':
        distinct = {row.slot: row for row in by_code.get('ADH05', [])}
        if len(distinct) >= 3:
            selected = list(distinct.values())[:3]
    elif code == 'MIL05':
        selected = [row for row in by_code.get('QUR05', []) if reading_target and row.slot == reading_target][:1]
    elif code == 'MIL06':
        days = {}
        for row in rows:
            if row.cap_bucket == 'service':
                days.setdefault(row.activity_date, row)
        if len(days) >= 3:
            selected = list(days.values())[:3]
    if not selected:
        raise ValidationError('The milestone needs verified underlying achievements. For reading, identify the completed approved reading target.')
    return [row.ledger_entry_id for row in selected]


def verified_winner(rule, house_id, results, active_house_ids):
    ids = [row['house'] for row in results]
    if len(ids) != len(set(ids)) or not set(ids) <= set(active_house_ids) or house_id not in ids:
        raise ValidationError('Record distinct valid houses and assessment marks, including the selected house.')
    if rule.mode == 'inspection' and set(ids) != set(active_house_ids):
        raise ValidationError('Daily inspection results must include every active participant house.')
    highest = max(row['marks'] for row in results)
    if next(row['marks'] for row in results if row['house'] == house_id) != highest:
        raise ValidationError('Only the highest-scoring house or tied winners receive the fixed bonus.')
    return [dict(house=row['house'], marks=format(row['marks'].normalize(), 'f')) for row in sorted(results, key=lambda row: row['house'])]


def eligible_members(edition, day=None, participant_id=None, house_id=None, lock=False):
    """Read existing eligibility; never prepare enrollment, IDs or check-ins."""
    allocations = list(HouseAllocation.objects.filter(edition=edition, status='allocated')
        .filter(**({'participant_id': participant_id} if participant_id else {}))
        .select_related('participant', 'house').order_by('participant_id'))
    counts = Counter(row.participant_id for row in allocations)
    allocations = [row for row in allocations if counts[row.participant_id] == 1
        and row.house.edition_id == edition.pk and row.house.purpose == 'participants'
        and row.house.status == 'active' and (house_id is None or row.house_id == house_id)]
    ids = [row.participant_id for row in allocations]
    sources = RegistrationOrderItem.objects.filter(participant_id__in=ids, order__edition=edition)
    source_ids = set(sources.values_list('pk', flat=True))
    if lock:
        list(RegistrationOrder.objects.select_for_update().filter(pk__in=sources.values('order_id')).order_by('pk'))
        list(Participant.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
        if set(sources.values_list('pk', flat=True)) != source_ids:
            raise ValidationError('Registration changed. Refresh and try again.')
    enrollment_query = CampEnrollment.objects.filter(edition=edition, participant_id__in=ids)
    if lock:
        enrollment_query = enrollment_query.select_for_update()
    enrollments = {row.participant_id: row for row in enrollment_query}
    arrivals = {row.participant_id: row for row in CampCheckIn.objects.filter(edition=edition, participant_id__in=ids)}
    items = {}
    for item in sources.select_related('order', 'category').order_by('pk'):
        items.setdefault(item.participant_id, item)
    result = []
    for allocation in allocations:
        pid = allocation.participant_id
        from .tutor_registration import is_tutor
        if is_tutor(pid, edition.pk):
            continue
        if pid not in arrivals or pid not in items:
            continue
        if day and timezone.localtime(arrivals[pid].checked_in_at, LAGOS_TIME_ZONE).date() > day:
            continue
        candidate = enrollments.get(pid) or SimpleNamespace(source_item_id=items[pid].pk,
            participant_id=pid, edition_id=edition.pk, source_review_fingerprint='', restriction_reason='')
        if eligibility(candidate)['eligible']:
            result.append(allocation)
    return result


def fingerprint(data, actor):
    payload = {key: value for key, value in data.items() if key != 'request_id'}
    payload['actor'] = actor.pk
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@transaction.atomic
def record_activity(edition, actor, data):
    require_scoring_staff(actor, 'can_record_dic_scores')
    require_activity_storage()
    edition = CampEdition.objects.select_for_update().get(pk=edition.pk)
    signature = fingerprint(data, actor)
    existing = HouseScoreTransaction.objects.filter(edition=edition, request_id=data['request_id']).first()
    if existing:
        award = ActivityAward.objects.filter(ledger_entry=existing).first()
        if not award or award.submission_fingerprint != signature:
            raise ValidationError('This submission reference was already used for different details.')
        return award, False
    rule = activity_for(data['activity'])
    if edition.year != 2026:
        raise ValidationError('This fixed activity policy is approved for DIC 2026 only.')
    day, slot = data['date'], data.get('slot', '')
    if not edition.camp_start_date <= day <= min(edition.camp_end_date, timezone.localdate(timezone=LAGOS_TIME_ZONE)):
        raise ValidationError('Choose a camp date that is not in the future.')
    if not data['verified']:
        raise ValidationError('An authorised officer must verify completion before awarding points.')
    key, exclusion = award_keys(rule, day, slot)
    evidence = dict(note=data.get('note', ''))
    participant_id, allocation = None, None
    points = rule.points
    if rule.kind == 'individual':
        if not data.get('participant') or data.get('house') or data.get('attendees') or data.get('exemptions') or data.get('results'):
            raise ValidationError('Select one camper; collective details are not allowed for an individual activity.')
        members = eligible_members(edition, day, participant_id=data['participant'], lock=True)
        if len(members) != 1:
            raise ValidationError('The camper must be verified-paid, checked in and have one valid house assignment.')
        allocation = members[0]
        participant_id, house_id = allocation.participant_id, allocation.house_id
        claims = ActivityAward.objects.filter(edition=edition, participant_id=participant_id)
        if claims.filter(entitlement_key=key).exists() or (exclusion and claims.filter(exclusion_key=exclusion).exists()):
            raise ValidationError('This activity, milestone or mutually exclusive prayer award is already recorded, including reversed claims.')
        if rule.cap_bucket:
            # Reversed claims remain reserved: no accidental repeat entitlement.
            used = sum(claims.filter(activity_date=day, cap_bucket=rule.cap_bucket).values_list('ledger_entry__points', flat=True))
            cap_check(rule.cap_bucket, used, points)
        if rule.frequency == 'target' and not data.get('note', '').strip():
            raise ValidationError('Document verification of the approved target, distinct task or incident.')
        if rule.mode == 'milestone':
            underlying = list(claims.filter(activity_date__lte=day,
                ledger_entry__reversal__isnull=True).order_by('activity_date', 'pk'))
            evidence['sources'] = milestone_sources(rule.code, underlying, data.get('reading_target', ''))
            evidence['reading_target'] = data.get('reading_target', '')
    else:
        if data.get('participant') or not data.get('house'):
            raise ValidationError('Select a house for a collective activity.')
        house = scoring_houses(edition).filter(pk=data['house'], status='active').first()
        if not house:
            raise ValidationError('Choose an active participant house in this edition.')
        house_id = house.pk
        if ActivityAward.objects.filter(edition=edition, house=house, kind='collective', entitlement_key=key).exists():
            raise ValidationError('This collective house achievement is already recorded, including reversed claims.')
        exemptions = data.get('exemptions', [])
        if exemptions:
            require_scoring_staff(actor, 'can_correct_dic_scores')
        if not data.get('note', '').strip():
            raise ValidationError('Document the inspection, attendance verification or competition result.')
        members = eligible_members(edition, day, house_id=house_id, lock=True)
        ids = {row.participant_id for row in members}
        attendees = data.get('attendees', [])
        if rule.mode not in ('participation', 'prayer_target') and (attendees or exemptions):
            raise ValidationError('Attendance and exemptions are only used for participation activities.')
        if rule.mode == 'prayer_target':
            # Four distinct punctuality claims from the five obligatory prayers.
            prayer_rows = ActivityAward.objects.filter(edition=edition, participant_id__in=ids,
                activity_date=day, activity_code__in=('SAL01', 'SAL02'),
                exclusion_key__startswith='punctuality:', ledger_entry__reversal__isnull=True)
            prayers = {}
            for row in prayer_rows:
                if row.slot in PRAYERS:
                    prayers.setdefault(row.participant_id, set()).add(row.slot)
            attendees = sorted(pid for pid, slots in prayers.items() if len(slots) >= 4)
            attendees = [pid for pid in attendees if pid not in {entry['participant'] for entry in exemptions}]
            evidence['sources'] = [row.ledger_entry_id for row in prayer_rows if row.participant_id in attendees and row.slot in PRAYERS]
        results = data.get('results', [])
        if rule.mode in ('inspection', 'competition'):
            evidence['results'] = verified_winner(rule, house_id, results,
                scoring_houses(edition).filter(status='active').values_list('pk', flat=True))
        elif results:
            raise ValidationError('Assessment marks are only used for inspections and competitions.')
        points, calculation = collective_points(rule, ids, exemptions, attendees)
        evidence.update(calculation, eligible=sorted(ids), exemptions=exemptions,
            attendees=attendees, threshold=rule.threshold)
        previous = ActivityAward.objects.filter(edition=edition, kind='collective', entitlement_key=key).first()
        if previous and rule.mode in ('inspection', 'competition') and previous.evidence.get('results') != evidence['results']:
            raise ValidationError('Results differ from those already verified for this occurrence. Use the same official results for tied winners.')
    context = allocation.participant.full_name if allocation else 'Collective house award'
    ledger_note = f'{context} · {day.isoformat()}' + (f' · {slot}' if slot else '')
    if data.get('note'):
        ledger_note += '\n' + data['note']
    ledger, created = append_score(edition, actor, data['request_id'], dict(house_id=house_id,
        entry_type='award', points=points, activity=rule.name, note=ledger_note, reverses_id=None))
    if not created:
        raise ValidationError('Submission conflict. Refresh and try again.')
    award = ActivityAward.objects.create(edition=edition, house_id=house_id,
        participant_id=participant_id, allocation=allocation, ledger_entry=ledger,
        kind=rule.kind, activity_code=rule.code, activity_date=day, slot=slot,
        entitlement_key=key, exclusion_key=exclusion, cap_bucket=rule.cap_bucket,
        evidence=json.loads(json.dumps(evidence, default=str)), submission_fingerprint=signature)
    return award, True


def check_reversal_dependencies(original):
    """Reverse earned bonuses before invalidating their prerequisite evidence."""
    if not activity_storage_ready():
        return
    award = ActivityAward.objects.filter(ledger_entry=original).first()
    if not award:
        return
    dependents = ActivityAward.objects.filter(edition=original.edition,
        ledger_entry__reversal__isnull=True).exclude(pk=award.pk)
    if any(original.pk in row.evidence.get('sources', []) for row in dependents):
        raise ValidationError('Reverse the dependent milestone or collective prayer bonus first, then reverse this underlying achievement.')
