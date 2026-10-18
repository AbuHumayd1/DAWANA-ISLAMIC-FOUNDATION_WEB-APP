import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .allocation import (
    AllocationError,
    allocate_participants,
    allocation_configuration_fingerprint,
    assign_participant,
    release_allocation,
    unallocated_paid_participants,
)
from .models import (
    CampEdition,
    DICAdminAuditEvent,
    House,
    HouseAllocation,
    PaymentAttempt,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)


class AllocationFixtures:
    def make_edition(self, year=2098):
        today = timezone.localdate()
        return CampEdition.objects.create(
            name=f"Allocation Camp {year}",
            year=year,
            camp_start_date=today + timedelta(days=30),
            camp_end_date=today + timedelta(days=36),
            registration_open_date=today - timedelta(days=5),
            registration_close_date=today + timedelta(days=20),
        )

    def make_participant(self, edition, *, sex=Participant.Sex.MALE, paid=True, name="Participant"):
        participant = Participant.objects.create(
            full_name=name,
            address="Test address",
            phone="+234000000000",
            email=f"{uuid.uuid4()}@example.test",
            date_of_birth=date(2000, 1, 1),
            sex=sex,
            height_cm=Decimal("170.00"),
            weight_kg=Decimal("65.00"),
            academic_status=Participant.AcademicStatus.TERTIARY,
            occupation=Participant.Occupation.BUSINESS,
            marital_status=Participant.MaritalStatus.SINGLE,
        )
        category = RegistrationCategory.objects.create(
            edition=edition,
            name=f"Category {uuid.uuid4()}",
            fee_ngn=Decimal("100.00"),
        )
        registrant = PrimaryRegistrant.objects.create(full_name="Guardian")
        order = RegistrationOrder.objects.create(
            primary_registrant=registrant,
            edition=edition,
            payment_status=(
                RegistrationOrder.PaymentStatus.PAID
                if paid
                else RegistrationOrder.PaymentStatus.PENDING
            ),
            status=(
                RegistrationOrder.Status.CONFIRMED
                if paid
                else RegistrationOrder.Status.SUBMITTED
            ),
            idempotency_key_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            request_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            access_token_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        )
        RegistrationOrderItem.objects.create(
            order=order,
            participant=participant,
            category=category,
            category_name_snapshot=category.name,
            fee_snapshot_ngn=category.fee_ngn,
            participant_snapshot={"full_name": participant.full_name},
        )
        if paid:
            PaymentAttempt.objects.create(
                order=order,
                reference=f"DIC-{uuid.uuid4()}",
                amount_kobo=10000,
                status=PaymentAttempt.Status.SUCCESSFUL,
            )
        return participant

    def make_house(
        self,
        edition,
        *,
        name="House",
        gender=House.Gender.MALE,
        purpose=House.Purpose.PARTICIPANTS,
        capacity=10,
        status=House.Status.ACTIVE,
        eligibility_rules=None,
    ):
        return House.objects.create(
            edition=edition,
            name=name,
            gender=gender,
            purpose=purpose,
            capacity=capacity,
            status=status,
            eligibility_rules=eligibility_rules or {},
        )

    def approve_balanced_strategy(self, edition):
        edition.allocation_strategy = CampEdition.AllocationStrategy.BALANCED
        edition.allocation_strategy_approved_at = timezone.now()
        edition.allocation_strategy_approval_note = "Committee approval recorded in test."
        edition.save(
            update_fields=(
                "allocation_strategy",
                "allocation_strategy_approved_at",
                "allocation_strategy_approval_note",
            )
        )
        edition.allocation_approved_configuration = allocation_configuration_fingerprint(
            edition
        )
        edition.save(update_fields=("allocation_approved_configuration",))


class HouseAllocationTests(AllocationFixtures, TestCase):
    def setUp(self):
        self.edition = self.make_edition()
        self.actor = get_user_model().objects.create_user(
            username="allocator",
        )

    def test_unpaid_participant_is_not_eligible_for_allocation(self):
        participant = self.make_participant(self.edition, paid=False)
        house = self.make_house(self.edition)

        with self.assertRaisesMessage(
            AllocationError,
            "no verified paid registration",
        ):
            assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)

        self.assertFalse(HouseAllocation.objects.exists())
        self.assertFalse(unallocated_paid_participants(self.edition).filter(pk=participant.pk).exists())

    def test_paid_status_without_successful_verified_attempt_is_not_eligible(self):
        participant = self.make_participant(self.edition, paid=False)
        item = participant.registration_items.get()
        RegistrationOrder.objects.filter(pk=item.order_id).update(
            payment_status=RegistrationOrder.PaymentStatus.PAID,
            status=RegistrationOrder.Status.CONFIRMED,
        )
        house = self.make_house(self.edition)

        with self.assertRaisesMessage(AllocationError, "no verified paid registration"):
            assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)

        self.assertFalse(HouseAllocation.objects.exists())

    def test_gender_must_match_and_editions_must_match(self):
        participant = self.make_participant(self.edition, sex=Participant.Sex.FEMALE)
        male_house = self.make_house(self.edition, gender=House.Gender.MALE)
        other_edition = self.make_edition(year=2099)
        other_house = self.make_house(other_edition, gender=House.Gender.FEMALE)

        with self.assertRaisesMessage(AllocationError, "does not match"):
            assign_participant(participant.pk, self.edition.pk, male_house.pk, self.actor)
        with self.assertRaisesMessage(AllocationError, "no verified paid registration"):
            assign_participant(participant.pk, other_edition.pk, other_house.pk, self.actor)

    def test_capacity_is_enforced(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(self.edition, capacity=0)

        with self.assertRaisesMessage(AllocationError, "reached its configured capacity"):
            assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)

    def test_house_capacity_cannot_be_reduced_below_occupancy(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(self.edition, capacity=1)
        assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)
        house.capacity = 0

        with self.assertRaises(ValidationError):
            house.full_clean()

    def test_inactive_and_unauthorized_reserve_houses_are_not_used(self):
        participant = self.make_participant(self.edition)
        inactive = self.make_house(self.edition, status=House.Status.INACTIVE)
        reserve = self.make_house(
            self.edition,
            name="Reserve",
            status=House.Status.RESERVE,
        )

        with self.assertRaisesMessage(AllocationError, "inactive"):
            assign_participant(participant.pk, self.edition.pk, inactive.pk, self.actor)
        with self.assertRaisesMessage(AllocationError, "not been authorised"):
            assign_participant(participant.pk, self.edition.pk, reserve.pk, self.actor)

    def test_dedicated_accommodation_requires_explicit_admin_eligibility(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(
            self.edition,
            purpose=House.Purpose.FATHERS_AND_ADMINS,
        )

        with self.assertRaisesMessage(AllocationError, "not been explicitly authorised"):
            assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)

        participant.eligible_for_dedicated_accommodation = True
        participant.save(update_fields=("eligible_for_dedicated_accommodation",))
        allocation = assign_participant(
            participant.pk,
            self.edition.pk,
            house.pk,
            self.actor,
            reason="Eligibility verified by an administrator.",
        )
        self.assertEqual(allocation.house, house)
        self.assertEqual(allocation.allocated_by, self.actor)

    def test_nonempty_house_rules_fail_closed_without_an_evaluator(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(
            self.edition,
            eligibility_rules={"committee_rule": "not-yet-defined"},
        )

        with self.assertRaisesMessage(AllocationError, "without an approved evaluator"):
            assign_participant(participant.pk, self.edition.pk, house.pk, self.actor)

    def test_batch_allocation_requires_approved_strategy_and_balances_occupancy(self):
        participants = [
            self.make_participant(self.edition, name=f"Participant {index}")
            for index in range(4)
        ]
        first = self.make_house(self.edition, name="House A", capacity=4)
        second = self.make_house(self.edition, name="House B", capacity=4)

        with self.assertRaisesMessage(AllocationError, "disabled"):
            allocate_participants(
                self.edition.pk,
                [participant.pk for participant in participants],
                self.actor,
            )

        self.approve_balanced_strategy(self.edition)
        allocations = allocate_participants(
            self.edition.pk,
            [participant.pk for participant in participants],
            self.actor,
        )
        self.assertEqual(len(allocations), 4)
        self.assertEqual(
            HouseAllocation.objects.filter(
                house=first,
                status=HouseAllocation.Status.ALLOCATED,
            ).count(),
            2,
        )
        self.assertEqual(
            HouseAllocation.objects.filter(
                house=second,
                status=HouseAllocation.Status.ALLOCATED,
            ).count(),
            2,
        )
        self.assertTrue(all(item.source == HouseAllocation.Source.SYSTEM for item in allocations))

    def test_stale_approval_blocks_automatic_allocation_after_configuration_changes(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(self.edition)
        self.approve_balanced_strategy(self.edition)
        house.capacity = 11
        house.save(update_fields=("capacity",))

        with self.assertRaisesMessage(AllocationError, "configured and approved"):
            allocate_participants(self.edition.pk, [participant.pk], self.actor)

    def test_authorized_reserve_is_available_only_after_strategy_reapproval(self):
        participant = self.make_participant(self.edition)
        reserve = self.make_house(
            self.edition,
            status=House.Status.RESERVE,
            capacity=1,
        )
        self.approve_balanced_strategy(self.edition)
        reserve.reserve_authorized_at = timezone.now()
        reserve.reserve_authorized_by = self.actor
        reserve.save(update_fields=("reserve_authorized_at", "reserve_authorized_by"))

        with self.assertRaisesMessage(AllocationError, "configured and approved"):
            allocate_participants(self.edition.pk, [participant.pk], self.actor)

        self.approve_balanced_strategy(self.edition)
        allocation = allocate_participants(self.edition.pk, [participant.pk], self.actor)[0]
        self.assertEqual(allocation.house, reserve)

    def test_reassignment_and_release_preserve_auditable_history(self):
        participant = self.make_participant(self.edition)
        first = self.make_house(self.edition, name="First")
        second = self.make_house(self.edition, name="Second")
        original = assign_participant(
            participant.pk,
            self.edition.pk,
            first.pk,
            self.actor,
            reason="Initial manual assignment.",
        )

        with self.assertRaisesMessage(AllocationError, "reason is required"):
            assign_participant(
                participant.pk,
                self.edition.pk,
                second.pk,
                self.actor,
                reassign=True,
            )
        replacement = assign_participant(
            participant.pk,
            self.edition.pk,
            second.pk,
            self.actor,
            reason="Committee-approved room change.",
            reassign=True,
        )
        original.refresh_from_db()
        self.assertEqual(original.status, HouseAllocation.Status.REASSIGNED)
        self.assertEqual(original.change_reason, "Initial manual assignment.")
        self.assertEqual(original.resolution_reason, "Committee-approved room change.")
        self.assertEqual(replacement.previous_allocation, original)

        with self.assertRaisesMessage(AllocationError, "reason is required"):
            release_allocation(replacement.pk, self.actor, "")
        release_allocation(replacement.pk, self.actor, "Participant withdrew.")
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, HouseAllocation.Status.RELEASED)
        self.assertEqual(replacement.change_reason, "Committee-approved room change.")
        self.assertEqual(replacement.resolution_reason, "Participant withdrew.")
        self.assertEqual(replacement.released_by, self.actor)
        self.assertIsNotNone(replacement.released_at)
        self.assertFalse(
            HouseAllocation.objects.filter(
                participant=participant,
                edition=self.edition,
                status=HouseAllocation.Status.ALLOCATED,
            ).exists()
        )
        later = assign_participant(
            participant.pk,
            self.edition.pk,
            first.pk,
            self.actor,
            reason="Participant reinstated.",
        )
        self.assertEqual(later.previous_allocation, replacement)

    def test_duplicate_active_allocation_is_rejected_by_database(self):
        participant = self.make_participant(self.edition)
        house = self.make_house(self.edition)
        first = assign_participant(
            participant.pk,
            self.edition.pk,
            house.pk,
            self.actor,
        )
        duplicate = HouseAllocation(
            participant=participant,
            edition=self.edition,
            house=house,
            status=HouseAllocation.Status.ALLOCATED,
            allocated_by=self.actor,
        )

        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

        self.assertEqual(
            HouseAllocation.objects.filter(
                participant=participant,
                edition=self.edition,
                status=HouseAllocation.Status.ALLOCATED,
            ).count(),
            1,
        )
        self.assertEqual(first.status, HouseAllocation.Status.ALLOCATED)


class AllocationAdminPermissionTests(AllocationFixtures, TestCase):
    def setUp(self):
        self.edition = self.make_edition()
        self.admin_user = get_user_model().objects.create_user(
            username="staff-without-allocation-perms",
            is_staff=True,
        )
        self.client.force_login(self.admin_user)

    def test_allocation_console_requires_explicit_permission(self):
        response = self.client.get(
            reverse(
                "admin:dic_campedition_allocation_console",
                args=(self.edition.pk,),
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_reserve_authorization_requires_explicit_permission(self):
        reserve = self.make_house(self.edition, status=House.Status.RESERVE)
        response = self.client.get(
            reverse("admin:dic_house_reserve_authorization", args=(reserve.pk,))
        )
        self.assertEqual(response.status_code, 403)

    def test_dedicated_accommodation_flag_requires_its_specific_permission(self):
        from django.contrib import admin

        model_admin = admin.site._registry[Participant]
        request = type("Request", (), {"user": self.admin_user})()
        self.assertIn(
            "eligible_for_dedicated_accommodation",
            model_admin.get_readonly_fields(request),
        )
        permission = Permission.objects.get(
            content_type__app_label="dic",
            codename="can_authorize_dedicated_accommodation",
        )
        self.admin_user.user_permissions.add(permission)
        request.user = get_user_model().objects.get(pk=self.admin_user.pk)
        self.assertNotIn(
            "eligible_for_dedicated_accommodation",
            model_admin.get_readonly_fields(request),
        )

    def test_authorized_allocation_console_displays_unallocated_paid_people(self):
        self.admin_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_allocate_participants",
            )
        )
        self.make_participant(self.edition, name="Paid Participant")
        response = self.client.get(
            reverse(
                "admin:dic_campedition_allocation_console",
                args=(self.edition.pk,),
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unallocated participants with paid registrations")
        self.assertContains(response, "Paid Participant")

    def test_strategy_approval_requires_explicit_permission_and_records_approval(self):
        self.admin_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_approve_allocation_strategy",
            )
        )
        self.edition.allocation_strategy = CampEdition.AllocationStrategy.BALANCED
        self.edition.save(update_fields=("allocation_strategy",))
        response = self.client.post(
            reverse(
                "admin:dic_campedition_approve_allocation_strategy",
                args=(self.edition.pk,),
            ),
            {"confirm": "yes", "reason": "Committee minute 12."},
        )
        self.assertEqual(response.status_code, 302)
        self.edition.refresh_from_db()
        self.assertIsNotNone(self.edition.allocation_strategy_approved_at)
        self.assertEqual(self.edition.allocation_strategy_approved_by, self.admin_user)
        self.assertEqual(
            self.edition.allocation_approved_configuration,
            allocation_configuration_fingerprint(self.edition),
        )

    def test_authorized_admin_can_activate_a_reserve_house(self):
        self.admin_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_activate_reserve_houses",
            )
        )
        reserve = self.make_house(self.edition, status=House.Status.RESERVE)
        response = self.client.post(
            reverse("admin:dic_house_reserve_authorization", args=(reserve.pk,)),
            {
                "action": "authorize",
                "confirm": "yes",
                "reason": "Committee approved activation.",
            },
        )
        self.assertEqual(response.status_code, 302)
        reserve.refresh_from_db()
        self.assertEqual(reserve.reserve_authorized_by, self.admin_user)
        self.assertIsNotNone(reserve.reserve_authorized_at)
        self.assertEqual(
            reserve.reserve_authorization_reason,
            "Committee approved activation.",
        )

    def test_admin_can_create_manual_allocation_with_allocation_permission(self):
        self.admin_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_allocate_participants",
            )
        )
        participant = self.make_participant(self.edition, name="Manual assignment")
        house = self.make_house(self.edition)
        response = self.client.post(
            reverse("admin:dic_houseallocation_add"),
            {
                "edition": self.edition.pk,
                "participant": participant.pk,
                "house": house.pk,
                "change_reason": "Administrator assigned participant.",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        allocation = HouseAllocation.objects.get(participant=participant)
        self.assertEqual(allocation.house, house)
        self.assertEqual(allocation.allocated_by, self.admin_user)
        self.assertEqual(allocation.source, HouseAllocation.Source.ADMIN)
        self.assertTrue(
            DICAdminAuditEvent.objects.filter(
                actor=self.admin_user,
                action="participant_allocated",
                target_id=str(allocation.pk),
            ).exists()
        )

    def test_authorized_admin_can_reassign_and_release_with_reasons(self):
        self.admin_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_reassign_allocations",
            ),
            Permission.objects.get(
                content_type__app_label="dic",
                codename="can_release_allocations",
            ),
        )
        participant = self.make_participant(self.edition, name="Reassignment")
        old_house = self.make_house(self.edition, name="Old House")
        new_house = self.make_house(self.edition, name="New House")
        original = assign_participant(
            participant.pk,
            self.edition.pk,
            old_house.pk,
            self.admin_user,
        )
        response = self.client.post(
            reverse("admin:dic_houseallocation_reassign", args=(original.pk,)),
            {
                "confirm": "yes",
                "house": new_house.pk,
                "reason": "Approved reassignment.",
            },
        )
        self.assertEqual(response.status_code, 302)
        original.refresh_from_db()
        self.assertEqual(original.status, HouseAllocation.Status.REASSIGNED)
        current = HouseAllocation.objects.get(
            participant=participant,
            status=HouseAllocation.Status.ALLOCATED,
        )
        response = self.client.post(
            reverse("admin:dic_houseallocation_release", args=(current.pk,)),
            {"confirm": "yes", "reason": "Allocation released by administrator."},
        )
        self.assertEqual(response.status_code, 302)
        current.refresh_from_db()
        self.assertEqual(current.status, HouseAllocation.Status.RELEASED)
        self.assertEqual(current.released_by, self.admin_user)

    def test_admin_change_forms_render_for_allocation_configuration(self):
        from django.contrib.auth import get_user_model

        superuser = get_user_model().objects.create_superuser(
            username="allocation-superuser",
            password=None,
            email="admin@example.test",
        )
        self.client.force_login(superuser)
        house = self.make_house(self.edition, name="Admin test house")
        urls = (
            reverse("admin:dic_campedition_change", args=(self.edition.pk,)),
            reverse("admin:dic_house_change", args=(house.pk,)),
            reverse("admin:dic_houseallocation_add"),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class ConcurrentHouseAllocationTests(AllocationFixtures, TransactionTestCase):
    reset_sequences = True

    def test_concurrent_requests_cannot_exceed_house_capacity(self):
        edition = self.make_edition()
        participants = [
            self.make_participant(edition, name=f"Concurrent {index}")
            for index in range(2)
        ]
        house = self.make_house(edition, capacity=1)
        self.approve_balanced_strategy(edition)
        actor = get_user_model().objects.create_user(username="concurrent-allocator")

        def allocate(participant_id):
            close_old_connections()
            try:
                actor_for_thread = get_user_model().objects.get(pk=actor.pk)
                try:
                    allocate_participants(edition.pk, [participant_id], actor_for_thread)
                    return "allocated"
                except AllocationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(allocate, [participant.pk for participant in participants])
            )

        self.assertCountEqual(results, ["allocated", "rejected"])
        self.assertEqual(
            HouseAllocation.objects.filter(
                house=house,
                status=HouseAllocation.Status.ALLOCATED,
            ).count(),
            1,
        )
