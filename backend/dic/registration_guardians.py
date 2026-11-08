"""Validate explicit declarations only; never infer guardians from contact similarity."""
from django.db import transaction
from django.core.exceptions import ValidationError
from .allocation import AllocationError
from .models import CampEdition, GuardianRelationship, PortalAccountBooking, HouseAllocation, HousingJob
from .housing_service import permitted, review_guardian
from .housing_policy import age_on
from .settlement_evidence import order_has_verified_settlement


@transaction.atomic
def approve_declared_guardians(edition_id, actor, limit=50):
    permitted(actor, 'can_approve_housing_guardians')
    edition = CampEdition.objects.select_for_update().get(pk=edition_id)
    relations = GuardianRelationship.objects.filter(edition=edition, status='pending',
        registration_declared=True).select_related('child', 'guardian').order_by('pk')
    approved = 0
    for relation in relations:
        # Both participants must belong to exactly one shared, verified paid order.
        candidates = list(PortalAccountBooking.objects.filter(order__edition=edition,
            order__items__participant=relation.child, revoked_at__isnull=True,
            account__user__is_active=True, account__user__is_staff=False,
            account__user__is_superuser=False).select_related('order__primary_registrant', 'account'))
        if len(candidates) != 1:
            continue
        binding = candidates[0]
        order, guardian = binding.order, relation.guardian
        from .participant_api import primary_contact_matches
        if (order.items.filter(participant=guardian).count() != 1
                or guardian.registration_items.filter(order__edition=edition).count() != 1
                or relation.child.registration_items.filter(order__edition=edition).count() != 1
                or not order_has_verified_settlement(order)
                or binding.account.contact_channel != 'email'
                or not primary_contact_matches(order, binding.account.contact_channel, binding.account.contact_digest)):
            continue
        try:
            age_valid = age_on(guardian, edition) >= 18 and age_on(relation.child, edition) <= 5
        except ValidationError:
            continue
        if (guardian.sex.lower() != 'female' or guardian.eligible_for_dedicated_accommodation
                or not age_valid
                or not guardian.email or guardian.email.strip().casefold() != binding.account.login_email
                or binding.account.login_email != order.primary_registrant.email.strip().casefold()
                or guardian.full_name.strip().casefold() != order.primary_registrant.full_name.strip().casefold()):
            continue  # Ambiguous identity/age is a hold, never an inferred approval.
        if HouseAllocation.objects.filter(edition=edition, participant=guardian, status='allocated').exclude(
                house__gender='female', house__status='active', house__purpose='participants').exists():
            continue
        try:
            review_guardian(relation.pk, actor, 'approved',
                'Automatic validation: explicit declaration, verified booking email, adult identity and paid shared booking.')
        except (AllocationError, ValidationError):
            continue
        from .housing_queue import retry
        ids = [guardian.pk, relation.child_id]
        for job in HousingJob.objects.filter(edition=edition, participant_id__in=ids,
                state='held', reason='A guardian relationship awaits approval; hold the entire group.'):
            retry(job.pk, actor, 'Explicit guardian declaration validated automatically.')
        approved += 1
        if approved >= limit:
            break
