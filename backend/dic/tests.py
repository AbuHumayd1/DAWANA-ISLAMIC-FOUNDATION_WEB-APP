import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    CampEdition,
    House,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)


class CampEditionTests(TestCase):
    def make_edition(self, **overrides):
        values = {
            "name": "Test Camp",
            "year": 2098,
            "camp_start_date": date(2098, 8, 1),
            "camp_end_date": date(2098, 8, 7),
            "registration_open_date": date(2098, 5, 1),
            "registration_close_date": date(2098, 7, 1),
        }
        values.update(overrides)
        return CampEdition.objects.create(**values)

    def test_historical_editions_can_coexist_with_one_active_edition(self):
        historical = self.make_edition(year=2097, name="Historical Camp")
        current = self.make_edition(year=2098, is_active=True)

        self.assertEqual(historical.registration_categories.count(), 0)
        self.assertEqual(current.houses.count(), 0)
        self.assertEqual(CampEdition.objects.filter(is_active=True).count(), 1)

    def test_only_one_edition_can_be_active(self):
        self.make_edition(year=2097, is_active=True)
        duplicate = CampEdition(
            name="Second Active Camp",
            year=2098,
            camp_start_date=date(2098, 8, 1),
            camp_end_date=date(2098, 8, 7),
            registration_open_date=date(2098, 5, 1),
            registration_close_date=date(2098, 7, 1),
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_database_rejects_a_second_active_edition(self):
        self.make_edition(year=2097, is_active=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_edition(year=2098, is_active=True)

    def test_invalid_date_ranges_are_rejected(self):
        edition = CampEdition(
            name="Invalid Dates",
            year=2098,
            camp_start_date=date(2098, 8, 7),
            camp_end_date=date(2098, 8, 1),
            registration_open_date=date(2098, 7, 1),
            registration_close_date=date(2098, 5, 1),
        )

        with self.assertRaises(ValidationError) as raised:
            edition.full_clean()

        self.assertIn("camp_end_date", raised.exception.message_dict)
        self.assertIn("registration_close_date", raised.exception.message_dict)

    def test_database_rejects_invalid_camp_date_range(self):
        self.make_edition()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampEdition.objects.filter(year=2098).update(
                camp_start_date=date(2098, 8, 7),
                camp_end_date=date(2098, 8, 1),
            )

    def test_general_information_must_be_an_object(self):
        edition = CampEdition(
            name="Invalid Information",
            year=2098,
            camp_start_date=date(2098, 8, 1),
            camp_end_date=date(2098, 8, 7),
            registration_open_date=date(2098, 5, 1),
            registration_close_date=date(2098, 7, 1),
            general_information=["not", "an", "object"],
        )

        with self.assertRaises(ValidationError):
            edition.full_clean()


class RegistrationCategoryTests(TestCase):
    def setUp(self):
        self.edition = CampEdition.objects.create(
            name="Category Test Camp",
            year=2098,
            camp_start_date=date(2098, 8, 1),
            camp_end_date=date(2098, 8, 7),
            registration_open_date=date(2098, 5, 1),
            registration_close_date=date(2098, 7, 1),
        )

    def make_category(self, **overrides):
        values = {
            "edition": self.edition,
            "name": "Test Category",
            "fee_ngn": Decimal("12500.00"),
        }
        values.update(overrides)
        return RegistrationCategory.objects.create(**values)

    def test_category_is_associated_with_edition_and_has_ngn_fee(self):
        category = self.make_category(minimum_age=10, maximum_age=16)

        self.assertEqual(category.edition, self.edition)
        self.assertEqual(category.fee_ngn, Decimal("12500.00"))
        self.assertEqual(self.edition.registration_categories.get(), category)

    def test_negative_fee_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_category(fee_ngn=Decimal("-1.00"))

    def test_reversed_age_range_is_rejected(self):
        category = RegistrationCategory(
            edition=self.edition,
            name="Invalid Age Range",
            minimum_age=17,
            maximum_age=12,
            fee_ngn=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            category.full_clean()

    def test_duplicate_category_name_is_rejected_per_edition(self):
        self.make_category()
        duplicate = RegistrationCategory(
            edition=self.edition,
            name="Test Category",
            fee_ngn=Decimal("13000.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_category_keeps_its_edition_protected_from_deletion(self):
        self.make_category()
        with self.assertRaises(ProtectedError):
            self.edition.delete()


class HouseTests(TestCase):
    def setUp(self):
        self.edition = CampEdition.objects.create(
            name="House Test Camp",
            year=2098,
            camp_start_date=date(2098, 8, 1),
            camp_end_date=date(2098, 8, 7),
            registration_open_date=date(2098, 5, 1),
            registration_close_date=date(2098, 7, 1),
        )

    def test_house_configuration_supports_unconfirmed_capacity_and_reserve(self):
        house = House.objects.create(
            edition=self.edition,
            name="Configurable House",
            gender=House.Gender.FEMALE,
            capacity=None,
            status=House.Status.RESERVE,
            eligibility_rules={"age_groups": ["administrator-configured"]},
        )

        self.assertIsNone(house.capacity)
        self.assertEqual(house.status, House.Status.RESERVE)
        self.assertEqual(self.edition.houses.get(), house)

    def test_negative_capacity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            House.objects.create(
                edition=self.edition,
                name="Invalid Capacity House",
                gender=House.Gender.MALE,
                capacity=-1,
            )

    def test_fathers_and_admin_accommodation_must_be_designated_male(self):
        house = House(
            edition=self.edition,
            name="Invalid Accommodation",
            gender=House.Gender.FEMALE,
            purpose=House.Purpose.FATHERS_AND_ADMINS,
            capacity=None,
        )

        with self.assertRaises(ValidationError):
            house.full_clean()

    def test_database_rejects_female_fathers_and_admin_accommodation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            House.objects.create(
                edition=self.edition,
                name="Invalid Accommodation",
                gender=House.Gender.FEMALE,
                purpose=House.Purpose.FATHERS_AND_ADMINS,
                capacity=None,
            )

    def test_eligibility_rules_must_be_an_object(self):
        house = House(
            edition=self.edition,
            name="Invalid Rules",
            gender=House.Gender.MALE,
            eligibility_rules=["not", "an", "object"],
        )

        with self.assertRaises(ValidationError):
            house.full_clean()


class DicAdminTests(TestCase):
    def test_configuration_models_are_registered_with_admin(self):
        self.assertTrue(admin.site.is_registered(CampEdition))
        self.assertTrue(admin.site.is_registered(RegistrationCategory))
        self.assertTrue(admin.site.is_registered(House))
        self.assertTrue(admin.site.is_registered(PrimaryRegistrant))
        self.assertTrue(admin.site.is_registered(Participant))
        self.assertTrue(admin.site.is_registered(RegistrationOrder))
        self.assertTrue(admin.site.is_registered(RegistrationOrderItem))

    def test_edition_admin_preserves_edition_records(self):
        model_admin = admin.site._registry[CampEdition]

        self.assertFalse(model_admin.has_delete_permission(RequestFactory().get("/admin/")))

    def test_edition_admin_route_is_available(self):
        response = self.client.get(reverse("admin:dic_campedition_changelist"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


class RegistrationApiTests(APITestCase):
    def setUp(self):
        self.today = timezone.localdate()
        camp_start = self.today + timedelta(days=30)
        self.edition = CampEdition.objects.create(
            name="API Test Camp",
            year=self.today.year,
            camp_start_date=camp_start,
            camp_end_date=camp_start + timedelta(days=6),
            registration_open_date=self.today - timedelta(days=1),
            registration_close_date=self.today + timedelta(days=1),
            registration_status=CampEdition.RegistrationStatus.OPEN,
            is_active=True,
        )
        self.category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Configured Category A",
            fee_ngn=Decimal("12500.25"),
        )
        self.other_category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Configured Category B",
            fee_ngn=Decimal("8300.00"),
        )
        self.headers = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}

    def participant_payload(self, **overrides):
        values = {
            "category_id": self.category.pk,
            "full_name": "Test Participant",
            "address": "Test Address",
            "phone": "+233200000000",
            "email": "participant@example.test",
            "date_of_birth": date(self.today.year - 20, 1, 1).isoformat(),
            "sex": Participant.Sex.MALE,
            "height_cm": "175",
            "weight_kg": "70",
            "academic_status": Participant.AcademicStatus.TERTIARY,
            "occupation": Participant.Occupation.BUSINESS,
            "marital_status": Participant.MaritalStatus.SINGLE,
        }
        values.update(overrides)
        return values

    def order_payload(self, participants=None, **overrides):
        values = {
            "primary_registrant": {
                "full_name": "Primary Registrant",
                "phone": "+233200000001",
                "email": "registrant@example.test",
            },
            "participants": participants or [self.participant_payload()],
        }
        values.update(overrides)
        return values

    def create_order(self, payload=None, key=None):
        return self.client.post(
            reverse("dic:order-create"),
            payload or self.order_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
        )

    def test_registration_options_return_active_edition_and_active_categories(self):
        inactive = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Unavailable Category",
            fee_ngn=Decimal("0.00"),
            is_active=False,
        )

        response = self.client.get(reverse("dic:registration-options"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["year"], self.edition.year)
        self.assertTrue(response.data["registration_is_open"])
        category_ids = {item["id"] for item in response.data["categories"]}
        self.assertEqual(category_ids, {self.category.pk, self.other_category.pk})
        self.assertNotIn(inactive.pk, category_ids)

    def test_registration_options_are_unavailable_without_an_active_edition(self):
        self.edition.is_active = False
        self.edition.save()

        response = self.client.get(reverse("dic:registration-options"))

        self.assertEqual(response.status_code, 404)

    def test_order_accepts_multiple_participants_and_calculates_total(self):
        second = self.participant_payload(
            full_name="Second Participant",
            email="second@example.test",
            category_id=self.other_category.pk,
            sex=Participant.Sex.FEMALE,
        )

        response = self.create_order(
            self.order_payload(participants=[self.participant_payload(), second])
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["currency"], "NGN")
        self.assertEqual(response.data["participant_count"], 2)
        self.assertEqual(response.data["total_amount_ngn"], "20800.25")
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertEqual(RegistrationOrderItem.objects.count(), 2)
        self.assertEqual(Participant.objects.count(), 2)
        self.assertEqual(PrimaryRegistrant.objects.count(), 1)

    def test_client_supplied_total_is_rejected(self):
        payload = self.order_payload()
        payload["total_amount_ngn"] = "0.01"

        response = self.create_order(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_order_fee_and_participant_identity_are_snapshotted(self):
        response = self.create_order()
        item = RegistrationOrderItem.objects.get()
        participant = item.participant
        self.category.fee_ngn = Decimal("99000.00")
        self.category.name = "Later Category Rename"
        self.category.save()
        participant.full_name = "Updated Profile Name"
        participant.save()

        detail = self.client.get(
            reverse("dic:order-detail", args=[response.data["order_id"]]),
            HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["items"][0]["fee_snapshot_ngn"], "12500.25")
        self.assertEqual(
            detail.data["items"][0]["category_name_snapshot"],
            "Configured Category A",
        )
        self.assertEqual(
            detail.data["items"][0]["participant_snapshot"]["full_name"],
            "Test Participant",
        )
        self.assertEqual(detail.data["total_amount_ngn"], "12500.25")

    def test_registration_order_item_snapshot_cannot_be_changed(self):
        self.create_order()
        item = RegistrationOrderItem.objects.get()
        item.fee_snapshot_ngn = Decimal("1.00")

        with self.assertRaises(ValidationError):
            item.save()

    def test_same_idempotency_key_and_payload_replays_without_duplicate_order(self):
        key = str(uuid.uuid4())
        payload = self.order_payload()

        first = self.create_order(payload=payload, key=key)
        retry = self.create_order(payload=payload, key=key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data["idempotent_replay"])
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(retry.data["access_token"], first.data["access_token"])
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertEqual(RegistrationOrderItem.objects.count(), 1)

    def test_reusing_idempotency_key_with_different_payload_conflicts(self):
        key = str(uuid.uuid4())
        first = self.create_order(key=key)
        changed = self.order_payload()
        changed["participants"][0]["full_name"] = "Different Participant"

        response = self.create_order(payload=changed, key=key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(RegistrationOrder.objects.count(), 1)

    def test_invalid_or_inactive_category_is_rejected_atomically(self):
        inactive = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Inactive Category",
            fee_ngn=Decimal("1.00"),
            is_active=False,
        )
        participants = [
            self.participant_payload(),
            self.participant_payload(
                full_name="Invalid Category Participant",
                email="invalid@example.test",
                category_id=inactive.pk,
            ),
        ]

        response = self.create_order(self.order_payload(participants=participants))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)
        self.assertEqual(RegistrationOrderItem.objects.count(), 0)
        self.assertEqual(Participant.objects.count(), 0)
        self.assertEqual(PrimaryRegistrant.objects.count(), 0)

    def test_database_error_during_order_creation_rolls_back_everything(self):
        participants = [
            self.participant_payload(),
            self.participant_payload(
                full_name="Second Participant",
                email="second@example.test",
                category_id=self.other_category.pk,
            ),
        ]
        create_item = RegistrationOrderItem.objects.create
        calls = 0

        def fail_after_first_item(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated item persistence failure")
            return create_item(**kwargs)

        with patch(
            "dic.views.RegistrationOrderItem.objects.create",
            side_effect=fail_after_first_item,
        ):
            with self.assertRaises(RuntimeError):
                self.create_order(self.order_payload(participants=participants))

        self.assertEqual(RegistrationOrder.objects.count(), 0)
        self.assertEqual(RegistrationOrderItem.objects.count(), 0)
        self.assertEqual(Participant.objects.count(), 0)
        self.assertEqual(PrimaryRegistrant.objects.count(), 0)

    def test_category_from_another_edition_is_rejected(self):
        other_edition = CampEdition.objects.create(
            name="Other API Camp",
            year=self.today.year + 1,
            camp_start_date=self.today + timedelta(days=365),
            camp_end_date=self.today + timedelta(days=371),
            registration_open_date=self.today - timedelta(days=1),
            registration_close_date=self.today + timedelta(days=1),
            registration_status=CampEdition.RegistrationStatus.OPEN,
        )
        other_category = RegistrationCategory.objects.create(
            edition=other_edition,
            name="Other Edition Category",
            fee_ngn=Decimal("100.00"),
        )

        response = self.create_order(
            self.order_payload(
                participants=[self.participant_payload(category_id=other_category.pk)]
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_order_creation_requires_registration_status_and_date_window(self):
        self.edition.registration_status = CampEdition.RegistrationStatus.PAUSED
        self.edition.save()

        response = self.create_order()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_order_creation_rejects_outside_registration_dates(self):
        self.edition.registration_open_date = self.today + timedelta(days=1)
        self.edition.registration_close_date = self.today + timedelta(days=3)
        self.edition.save()

        response = self.create_order()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_configured_age_eligibility_uses_registration_date(self):
        self.category.minimum_age = 21
        self.category.save()
        payload = self.participant_payload(
            date_of_birth=date(self.today.year - 18, 1, 1).isoformat()
        )

        response = self.create_order(self.order_payload(participants=[payload]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_order_details_require_order_access_token(self):
        created = self.create_order()
        url = reverse("dic:order-detail", args=[created.data["order_id"]])

        missing = self.client.get(url)
        invalid = self.client.get(url, HTTP_AUTHORIZATION="Bearer invalid-token")
        valid = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {created.data['access_token']}",
        )

        self.assertNotEqual(missing.status_code, 200)
        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data["order_id"], created.data["order_id"])
        self.assertIn("participant_snapshot", valid.data["items"][0])
        self.assertNotIn("access_token", valid.data)

    def test_order_reference_alone_does_not_authorize_access(self):
        created = self.create_order()
        response = self.client.get(
            reverse("dic:order-detail", args=[created.data["order_id"]])
        )

        self.assertNotEqual(response.status_code, 200)

    def test_order_list_endpoint_is_not_exposed(self):
        response = self.client.get(reverse("dic:order-create"))

        self.assertEqual(response.status_code, 405)

    def test_order_status_values_are_constrained_in_the_database(self):
        response = self.create_order()
        order = RegistrationOrder.objects.get(public_id=response.data["order_id"])

        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistrationOrder.objects.filter(pk=order.pk).update(status="unknown")
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistrationOrder.objects.filter(pk=order.pk).update(payment_status="unknown")

    def test_required_frontend_participant_fields_are_enforced(self):
        payload = self.participant_payload()
        del payload["marital_status"]

        response = self.create_order(self.order_payload(participants=[payload]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

    def test_primary_registrant_contact_fields_are_optional(self):
        response = self.create_order({"participants": [self.participant_payload()]})

        self.assertEqual(response.status_code, 201)
        registrant = PrimaryRegistrant.objects.get()
        self.assertEqual(registrant.full_name, "")
        self.assertEqual(registrant.phone, "")
        self.assertEqual(registrant.email, "")
