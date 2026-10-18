import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
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
    )
    configuration = {
        "strategy": edition.allocation_strategy,
        "houses": list(houses),
    }
    serialized = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def paid_participants(edition):
    paid_items = RegistrationOrderItem.objects.filter(
        participant_id=OuterRef("pk"),
        order__edition=edition,
        order__payment_status=RegistrationOrder.PaymentStatus.PAID,
        order__status=RegistrationOrder.Status.CONFIRMED,
        order__payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
    ).exclude(order__status=RegistrationOrder.Status.CANCELLED)
    return Participant.objects.annotate(
        has_paid_registration=Exists(paid_items),
    ).filter(has_paid_registration=True)


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
    if not RegistrationOrderItem.objects.filter(
        participant=participant,
        order__edition=edition,
        order__payment_status=RegistrationOrder.PaymentStatus.PAID,
        order__status=RegistrationOrder.Status.CONFIRMED,
        order__payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
    ).exclude(order__status=RegistrationOrder.Status.CANCELLED).exists():
        raise AllocationError(
            f"{participant.full_name} has no verified paid registration for this edition."
        )
    if house.edition_id != edition.pk:
        raise AllocationError("The selected house belongs to a different edition.")
    if participant.sex.lower() != house.gender:
        raise AllocationError(
            f"{participant.full_name} does not match the selected house designation."
        )
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
        if occupied >= house.capacity:
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
def assign_participant(
    participant_id,
    edition_id,
    house_id,
    actor,
    reason="",
    source=HouseAllocation.Source.ADMIN,
    reassign=False,
):
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
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
def release_allocation(allocation_id, actor, reason):
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


@transaction.atomic
def allocate_participants(edition_id, participant_ids, actor):
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    if (
        edition.allocation_strategy != CampEdition.AllocationStrategy.BALANCED
        or edition.allocation_strategy_approved_at is None
        or not edition.allocation_strategy_approval_note.strip()
        or edition.allocation_approved_configuration
        != allocation_configuration_fingerprint(edition)
    ):
        raise AllocationError(
            "Automatic allocation is disabled until this edition's strategy is "
            "configured and approved by an administrator."
        )

    selected_ids = _normalized_ids(participant_ids)
    try:
        participants = list(
            Participant.objects.filter(pk__in=selected_ids).order_by("full_name", "pk")
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise AllocationError("Participant selection is invalid.") from exc
    if len(participants) != len(selected_ids):
        raise AllocationError("One or more selected participants could not be found.")
    if not participants:
        raise AllocationError("Select at least one participant to allocate.")

    houses = list(
        House.objects.select_for_update()
        .filter(edition=edition)
        .exclude(status=House.Status.INACTIVE)
        .order_by("name", "pk")
    )
    active_ids = set(
        HouseAllocation.objects.filter(
            edition=edition,
            status=HouseAllocation.Status.ALLOCATED,
        ).values_list("participant_id", flat=True)
    )
    occupied = {
        house.pk: HouseAllocation.objects.filter(
            house=house,
            status=HouseAllocation.Status.ALLOCATED,
        ).count()
        for house in houses
    }
    allocations = []
    for participant in participants:
        if participant.pk in active_ids:
            raise AllocationError(
                f"{participant.full_name} already has an active allocation."
            )
        if not RegistrationOrderItem.objects.filter(
            participant=participant,
            order__edition=edition,
            order__payment_status=RegistrationOrder.PaymentStatus.PAID,
        ).exclude(order__status=RegistrationOrder.Status.CANCELLED).exists():
            raise AllocationError(
                f"{participant.full_name} has no verified paid registration for this edition."
            )
        gender = participant.sex.lower()
        eligible_houses = [
            house
            for house in houses
            if house.gender == gender
            and (
                house.status == House.Status.ACTIVE
                or house.reserve_authorized_at is not None
            )
            and not house.eligibility_rules
            and (
                house.purpose != House.Purpose.FATHERS_AND_ADMINS
                or participant.eligible_for_dedicated_accommodation
            )
            and (house.capacity is None or occupied[house.pk] < house.capacity)
        ]
        if not eligible_houses:
            raise AllocationError(
                f"No configured eligible house with capacity is available for "
                f"{participant.full_name}."
            )
        preferred_purpose = (
            House.Purpose.FATHERS_AND_ADMINS
            if participant.eligible_for_dedicated_accommodation
            else House.Purpose.PARTICIPANTS
        )
        eligible_houses.sort(
            key=lambda house: (
                house.purpose != preferred_purpose,
                occupied[house.pk],
                house.name.casefold(),
                house.pk,
            )
        )
        house = eligible_houses[0]
        allocation = _create_allocation(
            participant,
            edition,
            house,
            actor,
            HouseAllocation.Source.SYSTEM,
        )
        allocations.append(allocation)
        occupied[house.pk] += 1
        active_ids.add(participant.pk)
    return allocations
