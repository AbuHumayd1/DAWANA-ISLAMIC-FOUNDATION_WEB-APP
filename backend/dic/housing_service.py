"""Guardian-aware operations around the existing allocation primitives."""
from collections import Counter
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .allocation import (AllocationError, _assign_single, _release_single,
                         allocation_configuration_fingerprint, paid_participants)
from .housing_policy import age_on, age_band, validate_inventory
from .models import (CampEdition, Participant, House, HouseAllocation,
                     GuardianRelationship, HousingJob, DICAdminAuditEvent)


def permitted(actor, permission):
    if actor is None or not actor.is_active or not actor.is_staff or not actor.has_perm('dic.' + permission):
        raise PermissionDenied('An authorized housing supervisor is required.')


def audit(actor, action, target, details):
    DICAdminAuditEvent.objects.create(actor=actor, action=action, target_type=type(target).__name__,
                                    target_id=str(target.pk), details=details)


def snapshot(edition, members):
    return list(HouseAllocation.objects.filter(edition=edition, participant__in=members, status='allocated')
                .order_by('pk').values('id', 'house_id', 'participant_id'))


def json_snapshot(rows):
    return [{key: str(value) for key, value in row.items()} for row in rows]


def members_for(participant, edition, strict=True):
    relations = GuardianRelationship.objects.filter(edition=edition, status__in=['pending', 'approved'])
    child_link = relations.filter(child=participant).select_related('guardian').first()
    if child_link:
        root = child_link.guardian
    else:
        root = participant
        if strict and age_on(participant, edition) <= 5:
            raise AllocationError('Dependent child has no approved guardian; hold for supervisor review.')
    links = list(relations.filter(guardian=root).select_related('child').order_by('child_id'))
    members = [root] + [link.child for link in links]
    if strict:
        if any(link.status != 'approved' for link in links):
            raise AllocationError('A guardian relationship awaits approval; hold the entire group.')
        for link in links:
            link.full_clean()
        paid = set(paid_participants(edition).filter(pk__in=[p.pk for p in members]).values_list('pk', flat=True))
        if any(p.pk not in paid for p in members):
            raise AllocationError('Guardian/group member has no verified paid registration; hold the entire group.')
        if any(p.eligible_for_dedicated_accommodation for p in members):
            raise AllocationError('Dedicated accommodation policy is pending committee confirmation; hold for review.')
        for member in members:
            age_on(member, edition)
    return members


def check_group_house(edition, members, house):
    from .house_configuration import house_capacity_limit
    limit = house_capacity_limit(edition)
    if house.edition_id != edition.pk:
        raise AllocationError('The selected house belongs to a different edition.')
    if house.capacity is None or house.capacity > limit:
        raise AllocationError(f'Configure a capacity of at most {limit} occupants before allocating.')
    if edition.year == 2026 and house.status == 'reserve':
        raise AllocationError('No reserve participant houses are approved for DIC 2026.')
    if house.purpose != House.Purpose.PARTICIPANTS:
        raise AllocationError('Dedicated accommodation policy is pending committee confirmation; hold for review.')
    if house.status == 'inactive' or (house.status == 'reserve' and not (
            house.reserve_authorized_at and house.reserve_authorized_by_id and house.reserve_authorization_reason.strip())):
        raise AllocationError('House is inactive or reserve has not been authorised.')
    if house.eligibility_rules:
        raise AllocationError('House rules are configured without an approved evaluator.')
    if len(members) > 1 and (house.gender != 'female' or house.status != 'active'):
        raise AllocationError('Guardian groups require a regular active female house, never a reserve.')
    if members[0].sex.lower() != house.gender:
        raise AllocationError('Participant does not match the selected house designation.')
    occupants = HouseAllocation.objects.filter(house=house, status='allocated').exclude(participant__in=members).count()
    if occupants + len(members) > min(house.capacity, limit):
        raise AllocationError('House has reached its configured capacity; the group cannot fit without splitting.')


def set_group_jobs(edition, members, state, reason, actor):
    for job in HousingJob.objects.select_for_update().filter(edition=edition, participant__in=members).order_by('pk'):
        before = job.state
        job.state, job.reason, job.claimed_at = state, reason, None
        job.save(update_fields=['state', 'reason', 'claimed_at', 'updated_at'])
        audit(actor, 'housing_job_' + state, job, {'before': before, 'after': state, 'reason': reason})


@transaction.atomic
def assign_group(participant_id, edition_id, house_id, actor, reason='', source=HouseAllocation.Source.ADMIN, reassign=False):
    permitted(actor, 'can_reassign_allocations' if reassign else 'can_allocate_participants')
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    participant = Participant.objects.get(pk=participant_id)
    try:
        members = members_for(participant, edition)
        house = House.objects.select_for_update().get(pk=house_id)
        check_group_house(edition, members, house)
        before = snapshot(edition, members)
        if reassign and not reason.strip():
            raise AllocationError('A reason is required when reassigning a group.')
        if not reassign and any(row['participant_id'] == participant.pk for row in before):
            raise AllocationError('Participant already has an active allocation.')
        if not reassign and any(row['house_id'] != house.pk for row in before):
            raise AllocationError('Group already has an allocation elsewhere; use supervised reassignment.')
        results = []
        for member in members:  # Guardian first, so child validation sees the guardian.
            current = next((row for row in before if row['participant_id'] == member.pk), None)
            if current and current['house_id'] == house.pk:
                results.append(HouseAllocation.objects.get(pk=current['id']))
                continue
            results.append(_assign_single(member.pk, edition.pk, house.pk, actor, reason, source, reassign))
        after = snapshot(edition, members)
        audit(actor, 'housing_group_reassigned' if reassign else 'housing_group_assigned', edition,
              {'before': json_snapshot(before), 'after': json_snapshot(after), 'reason': reason})
        set_group_jobs(edition, members, 'completed', 'Assigned by supervisor/allocation process.', actor)
        return next(item for item in results if item.participant_id == participant.pk)
    except ValidationError as exc:
        raise AllocationError('; '.join(exc.messages)) from exc


@transaction.atomic
def release_group(allocation_id, actor, reason):
    permitted(actor, 'can_release_allocations')
    if not reason.strip():
        raise AllocationError('A reason is required to release a group.')
    selected = HouseAllocation.objects.get(pk=allocation_id)
    edition = CampEdition.objects.select_for_update().get(pk=selected.edition_id)
    if selected.status != 'allocated':
        raise AllocationError('Only an active allocation can be released.')
    members = members_for(selected.participant, edition, strict=False)
    before = snapshot(edition, members)
    for row in before:
        _release_single(row['id'], actor, reason)
    # Keep the group held until an explicit supervisor action; discovery cannot undo a release.
    for member in members:
        HousingJob.objects.get_or_create(edition=edition, participant=member)
    set_group_jobs(edition, members, 'held', 'Supervisor release: ' + reason, actor)
    audit(actor, 'housing_group_released', edition,
          {'before': json_snapshot(before), 'after': [], 'reason': reason})
    selected.refresh_from_db()
    return selected


@transaction.atomic
def review_guardian(relationship_id, actor, decision, reason):
    permitted(actor, 'can_approve_housing_guardians')
    if decision not in ('approved', 'rejected', 'revoked') or not reason.strip():
        raise AllocationError('Select a review decision and provide a reason.')
    edition_id = GuardianRelationship.objects.values_list('edition_id', flat=True).get(pk=relationship_id)
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    relation = GuardianRelationship.objects.select_for_update().select_related('child', 'guardian').get(pk=relationship_id)
    allowed = {'pending': ('approved', 'rejected'), 'approved': ('revoked',)}
    if decision not in allowed.get(relation.status, ()):
        raise AllocationError('Guardian review transition is not permitted; preserve history and create a new relationship.')
    if HouseAllocation.objects.filter(edition=edition, participant=relation.child, status='allocated').exists():
        raise AllocationError('Release the guardian group before changing an allocated child’s relationship.')
    if decision == 'approved':
        ids = {relation.child_id, relation.guardian_id}
        if set(paid_participants(edition).filter(pk__in=ids).values_list('pk', flat=True)) != ids:
            raise AllocationError('Both child and guardian need verified paid registration before approval.')
        if HouseAllocation.objects.filter(edition=edition, participant=relation.guardian, status='allocated').exclude(house__gender='female', house__status='active', house__purpose='participants').exists():
            raise AllocationError('Release or reassign the guardian to a regular female house first.')
    before = relation.status
    relation.status, relation.reason = decision, reason.strip()
    relation.reviewed_by, relation.reviewed_at = actor, timezone.now()
    if decision == 'approved':
        relation.approved_by, relation.approved_at = actor, relation.reviewed_at
    relation._supervised = True
    try:
        relation.save()
    except ValidationError as exc:
        raise AllocationError('; '.join(exc.messages)) from exc
    audit(actor, 'housing_guardian_reviewed', relation,
          {'before': before, 'after': decision, 'reason': reason, 'guardian_id': str(relation.guardian_id), 'child_id': str(relation.child_id)})
    return relation


def require_automation(edition):
    if (edition.allocation_strategy != 'balanced' or not edition.allocation_strategy_approved_at
            or not edition.allocation_strategy_approved_by_id
            or not edition.allocation_strategy_approval_note.strip()
            or edition.allocation_approved_configuration != allocation_configuration_fingerprint(edition)):
        raise AllocationError('Automatic allocation is disabled until configured and approved by a supervisor.')
    try:
        return validate_inventory(edition)
    except ValidationError as exc:
        raise AllocationError('; '.join(exc.messages)) from exc


@transaction.atomic
def allocate_batch(edition_id, participant_ids, actor):
    permitted(actor, 'can_allocate_participants')
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    houses = require_automation(edition)
    selected = sorted(set(str(pk) for pk in participant_ids))
    participants = list(Participant.objects.filter(pk__in=selected).order_by('date_of_birth', 'pk'))
    if not participants or len(participants) != len(selected):
        raise AllocationError('Participant selection is invalid.')
    done, results = set(), []
    for participant in participants:
        if participant.pk in done:
            continue
        try:
            members = members_for(participant, edition)
            before = snapshot(edition, members)
            existing_houses = {row['house_id'] for row in before}
            if len(existing_houses) > 1:
                raise AllocationError('Guardian group is split; supervisor reconciliation required.')
            if len(before) == len(members):
                house = House.objects.get(pk=next(iter(existing_houses)))
                check_group_house(edition, members, house)
                set_group_jobs(edition, members, 'completed', 'Existing group allocation verified.', actor)
                done.update(p.pk for p in members)
                continue
            eligible = []
            for house in houses:
                if existing_houses and house.pk not in existing_houses:
                    continue
                try:
                    check_group_house(edition, members, house)
                except AllocationError:
                    continue
                occupants = list(HouseAllocation.objects.filter(house=house, status='allocated').select_related('participant'))
                # Minimize matching-band pressure for ALL incoming group members,
                # then occupancy/name/PK. Safety and general-before-reserve win first.
                incoming = Counter(age_band(member, edition) for member in members)
                band_count = sum(incoming[age_band(row.participant, edition)] for row in occupants)
                eligible.append((house.status == 'reserve', band_count, len(occupants), house.name.casefold(), house.pk, house))
            if not eligible:
                raise AllocationError('No eligible house can fit the entire group; hold for supervisor review.')
            house = min(eligible, key=lambda row: row[:-1])[-1]
            # Pick an unallocated member if the guardian was already assigned.
            active = {row['participant_id'] for row in before}
            requested = next(p for p in members if p.pk not in active)
            assign_group(requested.pk, edition.pk, house.pk, actor, reason='Approved automatic age-band allocation.', source='system')
            results.extend(HouseAllocation.objects.filter(edition=edition, participant__in=members, status='allocated').exclude(pk__in=[row['id'] for row in before]))
            done.update(p.pk for p in members)
        except ValidationError as exc:
            raise AllocationError('; '.join(exc.messages)) from exc
    return results
