import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction, OperationalError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import (
    CampEdition,
    House,
    HouseAllocation,
    PaymentAttempt,
    Participant,
    RegistrationOrder,
    RegistrationOrderItem,
)


class AllocationError(Exception):
    pass


def _normalized_ids(values):
    try:
        return {str(value) for value in values}
    except (TypeError, ValueError) as exc:
        raise AllocationError("Participant selection is invalid.") from exc


def allocation_configuration_fingerprint(edition):
    houses = House.objects.filter(edition=edition).order_by("pk").values(
        "pk",
        "name",
        "gender",
        "purpose",
        "capacity",
        "status",
        "eligibility_rules",
        "reserve_authorized_at",
        "reserve_authorized_by_id",
        "reserve_authorization_reason",
    )
    configuration = {
        "strategy": edition.allocation_strategy,
        "housing_age_reference_date": edition.housing_age_reference_date,
        "policy": "dic-housing-2026-v1",
        "houses": list(houses),
    }
    serialized = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def paid_participants(edition, participant_ids=None):
    from .settlement_evidence import order_has_verified_settlement
    orders = RegistrationOrder.objects.filter(edition=edition, registration_basis='paid',
        status='confirmed', payment_status='paid').select_related('current_price_revision')
    if participant_ids is not None:
        orders = orders.filter(items__participant_id__in=participant_ids).distinct()
    verified = [order.pk for order in orders.iterator(chunk_size=100) if order_has_verified_settlement(order)]
    paid_items = RegistrationOrderItem.objects.filter(participant_id=OuterRef('pk'), order_id__in=verified)
    return Participant.objects.exclude(registration_items__order__edition=edition,
        registration_items__order__registration_basis='tutor').annotate(
        has_paid_registration=Exists(paid_items)).filter(has_paid_registration=True)


def unallocated_paid_participants(edition):
    active_allocations = HouseAllocation.objects.filter(
        participant_id=OuterRef("pk"),
        edition=edition,
        status=HouseAllocation.Status.ALLOCATED,
    )
    return (
        paid_participants(edition)
        .annotate(has_active_allocation=Exists(active_allocations))
        .filter(has_active_allocation=False)
        .order_by("full_name", "pk")
    )


def _validate_allocation(participant, edition, house):
    # Recheck trusted evidence inside the existing allocation transaction/locks.
    if not paid_participants(edition, [participant.pk]).filter(pk=participant.pk).exists():
        raise AllocationError(
            f"{participant.full_name} has no verified paid registration for this edition."
        )
    if house.edition_id != edition.pk:
        raise AllocationError("The selected house belongs to a different edition.")
    from .housing_policy import validate_occupant
    try:
        validate_occupant(participant, edition, house)
    except ValidationError as exc:
        raise AllocationError('; '.join(exc.messages)) from exc
    if house.status == House.Status.INACTIVE:
        raise AllocationError(f"{house.name} is inactive and cannot receive allocations.")
    if house.status == House.Status.RESERVE and not house.reserve_authorized_at:
        raise AllocationError(f"{house.name} is a reserve house that has not been authorised.")
    if house.eligibility_rules:
        raise AllocationError(
            f"{house.name} has configured eligibility rules without an approved evaluator."
        )
    if (
        house.purpose == House.Purpose.FATHERS_AND_ADMINS
        and not participant.eligible_for_dedicated_accommodation
    ):
        raise AllocationError(
            f"{participant.full_name} has not been explicitly authorised for "
            "dedicated accommodation."
        )
    if house.capacity is not None:
        occupied = HouseAllocation.objects.filter(
            house=house,
            status=HouseAllocation.Status.ALLOCATED,
        ).count()
        from .house_configuration import house_capacity_limit
        if occupied >= min(house.capacity, house_capacity_limit(edition)):
            raise AllocationError(f"{house.name} has reached its configured capacity.")


def _create_allocation(participant, edition, house, actor, source, reason="", previous=None):
    allocation = HouseAllocation(
        participant=participant,
        edition=edition,
        house=house,
        status=HouseAllocation.Status.ALLOCATED,
        allocated_by=actor,
        source=source,
        previous_allocation=previous,
        change_reason=reason,
    )
    try:
        allocation.full_clean()
    except ValidationError as exc:
        raise AllocationError("; ".join(exc.messages)) from exc
    allocation.save()
    return allocation


@transaction.atomic
def _assign_single(
    participant_id,
    edition_id,
    house_id,
    actor,
    reason="",
    source=HouseAllocation.Source.ADMIN,
    reassign=False,
):
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    # Housing already owns the edition lock. Never wait on a settlement/pricing
    # transaction that might need that edition: fail safely and let staff retry.
    try:
        with transaction.atomic():
            list(RegistrationOrder.objects.select_for_update(of=('self',), nowait=True).filter(
                items__participant_id=participant_id, edition_id=edition_id).order_by('pk'))
    except OperationalError as exc:
        if getattr(exc.__cause__, 'sqlstate', None) != '55P03':
            raise
        raise AllocationError('Payment evidence is being updated. Refresh and retry allocation.') from None
    participant = Participant.objects.get(pk=participant_id)
    house = House.objects.select_for_update().get(pk=house_id)
    current = (
        HouseAllocation.objects.select_for_update()
        .filter(
            participant=participant,
            edition=edition,
            status=HouseAllocation.Status.ALLOCATED,
        )
        .first()
    )
    if current and not reassign:
        raise AllocationError(f"{participant.full_name} already has an active allocation.")
    if current and current.house_id == house.pk:
        raise AllocationError(f"{participant.full_name} is already assigned to {house.name}.")
    previous_history = current or (
        HouseAllocation.objects.select_for_update()
        .filter(participant=participant, edition=edition)
        .order_by("-allocated_at", "-pk")
        .first()
    )
    if previous_history and not reason.strip():
        raise AllocationError("A reason is required when reassigning an allocation.")
    _validate_allocation(participant, edition, house)
    if current:
        current.status = HouseAllocation.Status.REASSIGNED
        current.resolution_reason = reason.strip()
        current.save(update_fields=("status", "resolution_reason"))
    return _create_allocation(
        participant,
        edition,
        house,
        actor,
        source,
        reason.strip(),
        previous=previous_history,
    )


@transaction.atomic
def _release_single(allocation_id, actor, reason):
    if not reason or not reason.strip():
        raise AllocationError("A reason is required to release an allocation.")
    edition_id = HouseAllocation.objects.values_list("edition_id", flat=True).get(
        pk=allocation_id
    )
    CampEdition.objects.select_for_update().get(pk=edition_id)
    allocation = HouseAllocation.objects.select_for_update().get(pk=allocation_id)
    if allocation.status != HouseAllocation.Status.ALLOCATED:
        raise AllocationError("Only an active allocation can be released.")
    allocation.status = HouseAllocation.Status.RELEASED
    allocation.resolution_reason = reason.strip()
    allocation.released_at = timezone.now()
    allocation.released_by = actor
    allocation.save(
        update_fields=("status", "resolution_reason", "released_at", "released_by")
    )
    return allocation


def allocate_participants(edition_id, participant_ids, actor):
    # Group-aware policy uses the existing locked assignment primitives.
    from .housing_service import allocate_batch
    return allocate_batch(edition_id, participant_ids, actor)


def assign_participant(participant_id, edition_id, house_id, actor, reason="",
                       source=HouseAllocation.Source.ADMIN, reassign=False):
    from .housing_service import assign_group
    return assign_group(participant_id, edition_id, house_id, actor, reason, source, reassign)


def release_allocation(allocation_id, actor, reason):
    from .housing_service import release_group
    return release_group(allocation_id, actor, reason)
