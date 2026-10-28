import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .allocation import AllocationError, allocate_participants, assign_participant, release_allocation
from .housing_policy import age_on, age_band, validate_inventory
from .housing_service import review_guardian
from .housing_queue import discover, claim, process_claim, retry, LEASE
from .models import House, HouseAllocation, GuardianRelationship, HousingJob, DICAdminAuditEvent
from .test_allocation import AllocationFixtures


class HousingFixtures(AllocationFixtures):
    def initialize(self):
        self.edition = self.make_edition()
        self.actor = get_user_model().objects.create_user(username='housing-supervisor', is_staff=True, is_superuser=True)
        self.approve_balanced_strategy(self.edition)

    def participant(self, *, age=30, sex='Female', name=None, paid=True):
        participant = self.make_participant(self.edition, name=name or str(uuid.uuid4()), sex=sex, paid=paid)
        participant.date_of_birth = date(2026 - age, 12, 23)
        participant.save(update_fields=['date_of_birth'])
        return participant

    def group(self, count=1, approve=True):
        guardian = self.participant()
        children, links = [], []
        for _ in range(count):
            child = self.participant(age=3, sex='Male')
            link = GuardianRelationship.objects.create(edition=self.edition, child=child, guardian=guardian, reason='Proposed relationship verified by supervisor.')
            if approve:
                review_guardian(link.pk, self.actor, 'approved', 'Approved mother/female guardian relationship.')
            children.append(child)
            links.append(link)
        return guardian, children, links

    def female_house(self):
        return House.objects.filter(edition=self.edition, gender='female', status='active').order_by('pk').first()


class Phase2HousingTests(HousingFixtures, TestCase):
    def setUp(self):
        self.initialize()

    def test_reference_date_and_all_age_boundaries(self):
        for age, expected in [(0, 0), (5, 0), (6, 1), (10, 1), (11, 2), (13, 2), (14, 3), (16, 3), (17, 4), (80, 4)]:
            person = self.participant(age=age)
            self.assertEqual(age_on(person, self.edition), age)
            self.assertEqual(age_band(person, self.edition), expected)
        person.date_of_birth = date(2020, 12, 24)
        self.assertEqual(age_on(person, self.edition), 5)
        person.date_of_birth = date(2027, 1, 1)
        with self.assertRaises(ValidationError):
            age_on(person, self.edition)
        self.edition.year = 2026
        self.edition.housing_age_reference_date = date(2026, 12, 24)
        with self.assertRaises(ValidationError):
            age_on(self.participant(), self.edition)

    def test_inventory_requires_real_complete_configuration(self):
        validate_inventory(self.edition)
        house = self.female_house()
        house.capacity = None
        house.save()
        with self.assertRaises(ValidationError):
            validate_inventory(self.edition)
        with self.assertRaises(AllocationError):
            allocate_participants(self.edition.pk, [self.participant().pk], self.actor)

    def test_capacity_25_is_hard_limit_for_supervisors_and_direct_save(self):
        house = self.female_house()
        for _ in range(25):
            assign_participant(self.participant().pk, self.edition.pk, house.pk, self.actor)
        with self.assertRaises(AllocationError):
            assign_participant(self.participant().pk, self.edition.pk, house.pk, self.actor, reason='Cannot override capacity.')
        with self.assertRaises(ValidationError):
            HouseAllocation.objects.create(edition=self.edition, house=house, participant=self.participant())
        self.assertEqual(house.allocations.filter(status='allocated').count(), 25)
        house.capacity = 26
        with self.assertRaises(ValidationError):
            house.full_clean()

    def test_multiple_male_dependents_share_regular_female_house(self):
        guardian, children, _ = self.group(count=2)
        allocations = allocate_participants(self.edition.pk, [children[0].pk], self.actor)
        self.assertEqual(len(allocations), 3)
        self.assertEqual(len({item.house_id for item in allocations}), 1)
        self.assertTrue(all(item.house.gender == 'female' and item.house.status == 'active' for item in allocations))
        self.assertEqual(set(item.participant_id for item in allocations), {guardian.pk, *(child.pk for child in children)})

    def test_missing_or_pending_guardian_never_allocates_child_independently(self):
        child = self.participant(age=5, sex='Male')
        with self.assertRaises(AllocationError):
            allocate_participants(self.edition.pk, [child.pk], self.actor)
        guardian, _, _ = self.group(approve=False)
        with self.assertRaises(AllocationError):
            assign_participant(guardian.pk, self.edition.pk, self.female_house().pk, self.actor)
        self.assertFalse(HouseAllocation.objects.exists())

    def test_unpaid_or_ineligible_guardian_holds_group(self):
        guardian, children, links = self.group(approve=False)
        guardian.sex = 'Male'
        guardian.save()
        with self.assertRaises(AllocationError):
            review_guardian(links[0].pk, self.actor, 'approved', 'Cannot approve male guardian.')
        guardian.sex = 'Female'
        guardian.save()
        from .models import RegistrationOrder
        RegistrationOrder.objects.filter(items__participant=guardian).update(payment_status='pending')
        with self.assertRaises(AllocationError):
            review_guardian(links[0].pk, self.actor, 'approved', 'Payment required.')

    def test_guardian_conflict_and_permission_and_audit(self):
        guardian, children, links = self.group()
        other = self.participant()
        with self.assertRaises(ValidationError):
            GuardianRelationship.objects.create(edition=self.edition, child=children[0], guardian=other, reason='Conflicting guardian.')
        staff = get_user_model().objects.create_user(username='unprivileged', is_staff=True)
        with self.assertRaises(PermissionDenied):
            review_guardian(links[0].pk, staff, 'revoked', 'Denied.')
        with self.assertRaises(PermissionDenied):
            assign_participant(other.pk, self.edition.pk, self.female_house().pk, staff)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('admin:dic_guardian_review', args=[links[0].pk])).status_code, 403)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='housing_guardian_reviewed', actor=self.actor).exists())

    def test_group_cannot_split_or_use_reserve_and_capacity_failure_is_atomic(self):
        guardian, children, _ = self.group(count=2)
        house = self.female_house()
        for _ in range(23):
            assign_participant(self.participant().pk, self.edition.pk, house.pk, self.actor)
        with self.assertRaises(AllocationError):
            assign_participant(children[0].pk, self.edition.pk, house.pk, self.actor)
        self.assertFalse(HouseAllocation.objects.filter(participant__in=[guardian, *children]).exists())
        reserve = House.objects.get(edition=self.edition, gender='female', status='reserve')
        reserve.reserve_authorized_at = timezone.now()
        reserve.reserve_authorized_by = self.actor
        reserve.reserve_authorization_reason = 'Authorized reserve; still forbidden for dependent groups.'
        reserve.save()
        with self.assertRaises(AllocationError):
            assign_participant(guardian.pk, self.edition.pk, reserve.pk, self.actor)

    def test_error_mid_group_rolls_back_guardian_and_audit(self):
        from .housing_service import _assign_single
        guardian, children, _ = self.group()
        def fail_child(*args, **kwargs):
            if args[0] == children[0].pk:
                raise AllocationError('Synthetic interruption.')
            return _assign_single(*args, **kwargs)
        with patch('dic.housing_service._assign_single', side_effect=fail_child):
            with self.assertRaises(AllocationError):
                assign_participant(guardian.pk, self.edition.pk, self.female_house().pk, self.actor)
        self.assertFalse(HouseAllocation.objects.exists())
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='housing_group_assigned').exists())

    def test_reassignment_release_and_revocation_preserve_group_history(self):
        guardian, children, links = self.group(count=2)
        first = assign_participant(guardian.pk, self.edition.pk, self.female_house().pk, self.actor)
        with self.assertRaises(AllocationError):
            review_guardian(links[0].pk, self.actor, 'revoked', 'Cannot detach an allocated child.')
        destination = House.objects.filter(edition=self.edition, gender='female', status='active').exclude(pk=first.house_id).first()
        assign_participant(children[0].pk, self.edition.pk, destination.pk, self.actor, reassign=True, reason='Supervisor group move.')
        self.assertEqual(HouseAllocation.objects.filter(status='reassigned').count(), 3)
        active = HouseAllocation.objects.get(participant=children[0], status='allocated')
        release_allocation(active.pk, self.actor, 'Guardian group withdrawal.')
        self.assertFalse(HouseAllocation.objects.filter(status='allocated').exists())
        self.assertEqual(HousingJob.objects.filter(state='held').count(), 3)
        review_guardian(links[0].pk, self.actor, 'revoked', 'Released group; relationship ended.')
        links[0].refresh_from_db()
        self.assertEqual(links[0].approved_by_id, self.actor.pk)
        self.assertIsNotNone(links[0].approved_at)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='housing_group_released', details__reason='Guardian group withdrawal.').exists())

    def test_age_six_allocates_independently_and_balances_age_band(self):
        people = [self.participant(age=6, sex='Male') for _ in range(8)]
        allocate_participants(self.edition.pk, [p.pk for p in people], self.actor)
        counts = [h.allocations.filter(status='allocated').count() for h in House.objects.filter(edition=self.edition, gender='male', status='active')]
        self.assertEqual(counts, [2, 2, 2, 2])
        # A different band starts with the same deterministic house tie-break.
        newcomer = self.participant(age=17, sex='Male')
        result = allocate_participants(self.edition.pk, [newcomer.pk], self.actor)
        self.assertEqual(result[0].house, House.objects.filter(edition=self.edition, gender='male', status='active').order_by('name', 'pk').first())

    def test_reserve_cannot_be_reclassified_to_bypass_authorization(self):
        reserve = House.objects.get(edition=self.edition, gender='male', status='reserve')
        reserve.status, reserve.reserve_designation = 'active', False
        with self.assertRaises(ValidationError):
            reserve.save()

    def test_dedicated_participant_is_held_and_category_retained(self):
        person = self.participant(sex='Male')
        person.eligible_for_dedicated_accommodation = True
        person.save()
        house = self.make_house(self.edition, name='Synthetic dedicated test house', purpose=House.Purpose.FATHERS_AND_ADMINS)
        with self.assertRaises(AllocationError):
            assign_participant(person.pk, self.edition.pk, house.pk, self.actor)
        discover(self.edition.pk, self.actor)
        process_claim(*claim(self.edition.pk, self.actor), self.actor)
        self.assertEqual(HousingJob.objects.get(participant=person).state, 'held')
        self.assertTrue(House.objects.filter(pk=house.pk).exists())

    def test_queue_discovery_idempotency_group_completion_and_no_duplicate_allocation(self):
        guardian, children, _ = self.group()
        self.assertEqual(discover(self.edition.pk, self.actor), 2)
        self.assertEqual(discover(self.edition.pk, self.actor), 0)
        job_id, token = claim(self.edition.pk, self.actor)
        self.assertEqual(process_claim(job_id, token, self.actor), 'completed')
        self.assertEqual(process_claim(job_id, token, self.actor), 'completed')
        self.assertEqual(HousingJob.objects.filter(state='completed').count(), 2)
        self.assertEqual(HouseAllocation.objects.filter(status='allocated').count(), 2)

    def test_queue_policy_hold_explicit_retry_and_failure_recovery(self):
        guardian, children, links = self.group(approve=False)
        discover(self.edition.pk, self.actor)
        job_id, token = claim(self.edition.pk, self.actor)
        self.assertEqual(process_claim(job_id, token, self.actor), 'held')
        self.assertEqual(discover(self.edition.pk, self.actor), 0)
        review_guardian(links[0].pk, self.actor, 'approved', 'Approval completed.')
        retry(job_id, self.actor, 'Guardian approval resolved.')
        with patch('dic.housing_queue.allocate_batch', side_effect=RuntimeError('Synthetic private failure payload')):
            claimed = claim(self.edition.pk, self.actor)
            self.assertEqual(process_claim(*claimed, self.actor), 'failed')
        job = HousingJob.objects.get(pk=claimed[0])
        self.assertNotIn('private failure payload', job.reason)
        retry(job.pk, self.actor, 'Technical fault resolved.')
        self.assertEqual(process_claim(*claim(self.edition.pk, self.actor), self.actor), 'completed')

    def test_expired_claim_recovery_invalidates_old_token(self):
        self.participant()
        discover(self.edition.pk, self.actor)
        job_id, old_token = claim(self.edition.pk, self.actor)
        HousingJob.objects.filter(pk=job_id).update(claimed_at=timezone.now() - LEASE - timedelta(seconds=1))
        recovered_id, new_token = claim(self.edition.pk, self.actor)
        self.assertEqual(recovered_id, job_id)
        self.assertNotEqual(new_token, old_token)
        self.assertEqual(process_claim(job_id, old_token, self.actor), 'processing')
        self.assertEqual(process_claim(job_id, new_token, self.actor), 'completed')

    def test_admin_models_and_readonly_queue_render(self):
        self.assertIn(GuardianRelationship, admin.site._registry)
        self.assertIn(HousingJob, admin.site._registry)
        self.client.force_login(self.actor)
        for name in ('guardianrelationship', 'housingjob'):
            self.assertEqual(self.client.get(reverse(f'admin:dic_{name}_changelist')).status_code, 200)

    def test_worker_command_is_bounded_and_requires_exact_database_confirmation(self):
        self.participant()
        self.participant()
        options = dict(edition=self.edition.pk, actor=self.actor.pk, limit=1, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('process_housing_allocations', database_name='wrong_target', **options)
        self.assertFalse(HousingJob.objects.exists())
        name = connection.settings_dict['NAME']
        call_command('process_housing_allocations', database_name=name, discover_only=True, **options)
        self.assertEqual(HousingJob.objects.filter(state='pending').count(), 1)
        self.assertFalse(HouseAllocation.objects.exists())
        call_command('process_housing_allocations', database_name=name, **options)
        self.assertEqual(HouseAllocation.objects.filter(status='allocated').count(), 1)
        self.assertEqual(HousingJob.objects.filter(state='pending').count(), 1)


class ConcurrentHousingQueueTests(HousingFixtures, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update_skip_locked')
    def test_two_workers_cannot_duplicate_or_split_guardian_group(self):
        self.initialize()
        self.group(count=2)
        discover(self.edition.pk, self.actor)
        actor_id, edition_id = self.actor.pk, self.edition.pk
        def worker(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                item = claim(edition_id, actor)
                return process_claim(*item, actor) if item else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker, range(2)))
        self.assertIn('completed', outcomes)
        active = HouseAllocation.objects.filter(status='allocated')
        self.assertEqual(active.count(), 3)
        self.assertEqual(active.values('house_id').distinct().count(), 1)
