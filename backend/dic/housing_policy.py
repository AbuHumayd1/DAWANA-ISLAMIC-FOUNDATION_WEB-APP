"""Approved housing policy. No inferred guardians, inventory or payment changes."""
from datetime import date
from django.core.exceptions import ValidationError
from .house_configuration import house_capacity_limit

AGE_BANDS = ((0, 5), (6, 10), (11, 13), (14, 16), (17, None))


def age_reference(edition):
    reference = edition.housing_age_reference_date
    if reference is None:
        raise ValidationError('Configure the edition housing age reference date before allocating.')
    if edition.year == 2026 and reference != date(2026, 12, 23):
        raise ValidationError('DIC 2026 housing age reference date must be 23 December 2026.')
    return reference


def age_on(participant, edition):
    reference = age_reference(edition)
    birth = participant.date_of_birth
    if birth is None:
        raise ValidationError('Exact DOB withheld: age-dependent housing/guardian policy requires authorized review.')
    if birth > reference:
        raise ValidationError('Date of birth is after the housing age reference date.')
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def age_band(participant, edition):
    age = age_on(participant, edition)
    return next(index for index, (low, high) in enumerate(AGE_BANDS) if age >= low and (high is None or age <= high))


def validate_inventory(edition):
    from .models import House, HouseAllocation
    # A real date and real house records must be reviewed before approving automation.
    if not edition.housing_age_reference_date:
        raise ValidationError('Housing age reference date is not configured.')
    if edition.year == 2026 and edition.housing_age_reference_date != date(2026, 12, 23):
        raise ValidationError('DIC 2026 housing age reference date must be 23 December 2026.')
    houses = list(House.objects.filter(edition=edition, purpose=House.Purpose.PARTICIPANTS).exclude(status=House.Status.INACTIVE))
    final_2026 = edition.year == 2026
    limit = house_capacity_limit(edition)
    if len(houses) != (8 if final_2026 else 10):
        raise ValidationError('Verify exactly eight active participant houses without reserves for DIC 2026.' if final_2026 else 'Verify exactly eight operational general houses and two reserves.')
    from .allocation import paid_participants
    paid_ids = set(paid_participants(edition).values_list('pk', flat=True))
    for gender in ('male', 'female'):
        if sum(h.gender == gender and h.status == House.Status.ACTIVE for h in houses) != 4 or sum(h.gender == gender and h.status == House.Status.RESERVE for h in houses) != (0 if final_2026 else 1):
            raise ValidationError('DIC 2026 requires four active houses per sex and no reserves.' if final_2026 else 'Verify four active general houses and one reserve house per sex before approving allocation.')
    for house in houses:
        if not house.name.strip() or house.capacity != limit or house.eligibility_rules:
            raise ValidationError(f'Every operational house needs a verified name, capacity {limit} and supported eligibility rules.')
        occupants = list(HouseAllocation.objects.filter(house=house, status='allocated').select_related('participant'))
        if len(occupants) > limit:
            raise ValidationError(f'Existing house occupancy exceeds {limit}; supervisor reconciliation required.')
        for allocation in occupants:
            if allocation.participant_id not in paid_ids:
                raise ValidationError('Existing allocation lacks verified payment; supervisor reconciliation required.')
            validate_occupant(allocation.participant, edition, house)
    return houses


def validate_occupant(participant, edition, house):
    """Shared model/service validation; the caller locks the edition for writes."""
    from .models import GuardianRelationship, HouseAllocation
    from .tutor_registration import is_tutor
    if is_tutor(participant.pk, edition.pk):
        raise ValidationError('Tutor accommodation is managed offline; camper housing is unavailable.')
    if participant.eligible_for_dedicated_accommodation or house.purpose != 'participants':
        raise ValidationError('Dedicated accommodation policy is pending committee confirmation; hold for review.')
    limit = house_capacity_limit(edition)
    if house.capacity is None or house.capacity > limit:
        raise ValidationError(f'Configure a house capacity of at most {limit} before allocating.')
    if edition.year == 2026 and house.status == 'reserve':
        raise ValidationError('No reserve participant houses are approved for DIC 2026.')
    if house.status == 'inactive' or (house.status == 'reserve' and not (
            house.reserve_authorized_at and house.reserve_authorized_by_id and house.reserve_authorization_reason.strip())):
        raise ValidationError('House is inactive or reserve has not been authorised with a supervisor and reason.')
    age = age_on(participant, edition)
    if age <= 5:
        relation = GuardianRelationship.objects.filter(edition=edition, child=participant, status='approved').select_related('guardian').first()
        if not relation:
            raise ValidationError('Dependent child requires an approved female guardian; hold for review.')
        guardian = relation.guardian
        if guardian.sex.lower() != 'female' or age_on(guardian, edition) < 6 or guardian.eligible_for_dedicated_accommodation:
            raise ValidationError('Approved guardian is no longer eligible; hold for review.')
        from .allocation import paid_participants
        if not paid_participants(edition).filter(pk=guardian.pk).exists():
            raise ValidationError('Guardian no longer has verified paid registration; hold for review.')
        if house.gender != 'female' or house.status != 'active':
            raise ValidationError('Dependent groups require a regular active female house; reserves are not allowed.')
        if not HouseAllocation.objects.filter(edition=edition, participant=guardian, house=house, status='allocated').exists():
            raise ValidationError('Dependent must share the approved guardian’s active allocation.')
    elif participant.sex.lower() != house.gender:
        raise ValidationError('Participant does not match the selected house designation.')
