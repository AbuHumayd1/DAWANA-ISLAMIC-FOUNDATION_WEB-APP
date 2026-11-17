"""Workerless housing is isolated from payment and scoped to verified bookings."""
from unittest.mock import patch
from datetime import date
from django.utils import timezone

from django.test import TestCase, override_settings

from .allocation import unallocated_paid_participants
from .housing_queue import claim_for_participants
from .housing_self_service import housing_public_state, process_authorized_housing
from .models import HouseAllocation, HousingJob, RegistrationOrder
from .test_housing_phase2 import HousingFixtures


class PortalHousingTests(HousingFixtures, TestCase):
    def setUp(self):
        self.initialize()

    def test_verified_paid_portal_request_assigns_one_camper_without_worker(self):
        camper = self.participant(age=27)
        order = camper.registration_items.first().order
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'processed')
            self.assertEqual(process_authorized_housing([order]), 'awaiting')
        self.assertEqual(HouseAllocation.objects.filter(participant=camper, status='allocated').count(), 1)
        self.assertEqual(HousingJob.objects.get(participant=camper).state, 'completed')
        self.assertEqual(housing_public_state(camper.pk, self.edition, True)['status'], 'assigned')
        self.assertEqual(order.payment_status, 'paid')

    def test_failed_allocation_is_awaiting_not_a_payment_failure(self):
        camper = self.participant(age=27)
        order = camper.registration_items.first().order
        # Deliberately invalidate the approval fingerprint, so no allocation
        # is attempted and no financial records are written.
        self.edition.allocation_approved_configuration = '0' * 64
        self.edition.save(update_fields=['allocation_approved_configuration'])
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'awaiting')
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.status, 'confirmed')
        self.assertFalse(HouseAllocation.objects.filter(participant=camper).exists())
        self.assertEqual(housing_public_state(camper.pk, self.edition, False),
                         {'status': 'awaiting', 'message': 'Awaiting house allocation'})

    def test_scope_never_claims_another_paid_camper(self):
        authorized = self.participant(age=24)
        unrelated = self.participant(age=24)
        unrelated_job = HousingJob.objects.create(edition=self.edition, participant=unrelated)
        authorized_order = authorized.registration_items.first().order
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([authorized_order]), 'processed')
        unrelated_job.refresh_from_db()
        self.assertEqual(unrelated_job.state, 'pending')
        self.assertFalse(HouseAllocation.objects.filter(participant=unrelated).exists())

    def test_held_case_is_not_reset_by_portal_requests(self):
        camper = self.participant(age=25)
        order = camper.registration_items.first().order
        job = HousingJob.objects.create(edition=self.edition, participant=camper,
                                        state='held', reason='Guardian review required')
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'awaiting')
        job.refresh_from_db()
        self.assertEqual(job.state, 'held')
        self.assertEqual(job.reason, 'Guardian review required')
        self.assertFalse(HouseAllocation.objects.filter(participant=camper).exists())

    def test_without_actor_portal_still_reports_awaiting(self):
        camper = self.participant(age=20)
        order = camper.registration_items.first().order
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=0):
            self.assertEqual(process_authorized_housing([order]), 'awaiting')
        self.assertEqual(order.payment_status, 'paid')

    def _set_up_independent_dic2026(self):
        from .models import CampEdition
        from .management.commands.initialize_dic2026_release import initialize
        from .allocation import allocation_configuration_fingerprint
        self.edition = CampEdition.objects.create(
            name='DIC 2026 independent-housing regression', year=2026,
            camp_start_date=date(2026, 12, 23),
            camp_end_date=date(2027, 1, 1),
            housing_age_reference_date=date(2026, 12, 23))
        initialize(self.edition, self.actor)
        self.edition.allocation_strategy = 'balanced'
        self.edition.allocation_strategy_approved_at = timezone.now()
        self.edition.allocation_strategy_approved_by = self.actor
        self.edition.allocation_strategy_approval_note = 'Synthetic approved allocation test.'
        self.edition.save()
        self.edition.allocation_approved_configuration = allocation_configuration_fingerprint(self.edition)
        self.edition.save(update_fields=['allocation_approved_configuration'])

    def test_dic2026_paid_child_assigns_independently_without_guardian(self):
        self._set_up_independent_dic2026()
        child = self.participant(age=3, sex='Male')
        order = child.registration_items.first().order
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'processed')
        allocation = HouseAllocation.objects.get(participant=child, status='allocated')
        self.assertEqual(allocation.house.gender, 'male')
        self.assertEqual(HousingJob.objects.get(participant=child).state, 'completed')
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'paid')

    def test_dic2026_pending_guardian_relationship_does_not_block_housing(self):
        from .models import GuardianRelationship
        self._set_up_independent_dic2026()
        guardian = self.participant(age=30, sex='Female')
        child = self.participant(age=3, sex='Male')
        relation = GuardianRelationship.objects.create(
            edition=self.edition, child=child, guardian=guardian,
            reason='Unreviewed declaration must not block DIC 2026 housing.')
        order = child.registration_items.first().order
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'processed')
        self.assertEqual(relation.status, 'pending')
        self.assertEqual(HouseAllocation.objects.get(participant=child, status='allocated').house.gender, 'male')
        self.assertFalse(HouseAllocation.objects.filter(participant=guardian).exists())

    def test_dic2026_legacy_guardian_hold_recovers_but_other_holds_stay_held(self):
        self._set_up_independent_dic2026()
        child = self.participant(age=4, sex='Female')
        order = child.registration_items.first().order
        job = HousingJob.objects.create(
            edition=self.edition, participant=child, state='held',
            reason='Dependent child has no approved guardian; hold for supervisor review.')
        other = self.participant(age=25)
        other_job = HousingJob.objects.create(
            edition=self.edition, participant=other, state='held',
            reason='Supervisor release: retained for review.')
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.actor.pk):
            self.assertEqual(process_authorized_housing([order]), 'processed')
        job.refresh_from_db()
        other_job.refresh_from_db()
        self.assertEqual(job.state, 'completed')
        self.assertEqual(other_job.state, 'held')
        self.assertEqual(HouseAllocation.objects.get(participant=child, status='allocated').house.gender, 'female')
        self.assertEqual(order.payment_status, 'paid')
