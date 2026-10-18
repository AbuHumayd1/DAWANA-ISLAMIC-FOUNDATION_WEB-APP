import uuid
import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import RequestFactory
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    CampEdition,
    House,
    PaymentAttempt,
    PaystackWebhookEvent,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)
from .payment_views import _apply_verified_transaction
from .payments import PaystackClient, PaystackTransportError


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
        self.assertTrue(admin.site.is_registered(PaymentAttempt))
        self.assertTrue(admin.site.is_registered(PaystackWebhookEvent))

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
        self.assertNotEqual(retry.data["access_token"], first.data["access_token"])
        old_token_detail = self.client.get(
            reverse("dic:order-detail", args=[first.data["order_id"]]),
            HTTP_AUTHORIZATION=f"Bearer {first.data['access_token']}",
        )
        new_token_detail = self.client.get(
            reverse("dic:order-detail", args=[retry.data["order_id"]]),
            HTTP_AUTHORIZATION=f"Bearer {retry.data['access_token']}",
        )
        self.assertEqual(old_token_detail.status_code, 404)
        self.assertEqual(new_token_detail.status_code, 200)
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

    def test_expired_or_revoked_order_access_token_is_rejected(self):
        created = self.create_order()
        order = RegistrationOrder.objects.get(public_id=created.data["order_id"])
        url = reverse("dic:order-detail", args=[created.data["order_id"]])
        headers = {
            "HTTP_AUTHORIZATION": f"Bearer {created.data['access_token']}",
        }

        order.access_token_expires_at = timezone.now() - timedelta(seconds=1)
        order.save(update_fields=("access_token_expires_at",))
        expired = self.client.get(url, **headers)
        self.assertEqual(expired.status_code, 404)

        order.access_token_expires_at = timezone.now() + timedelta(days=1)
        order.access_token_revoked_at = timezone.now()
        order.save(update_fields=("access_token_expires_at", "access_token_revoked_at"))
        revoked = self.client.get(url, **headers)
        self.assertEqual(revoked.status_code, 404)

    def test_idempotent_replay_cannot_restore_revoked_order_access(self):
        key = str(uuid.uuid4())
        created = self.create_order(key=key)
        order = RegistrationOrder.objects.get(public_id=created.data["order_id"])
        order.access_token_revoked_at = timezone.now()
        order.save(update_fields=("access_token_revoked_at",))

        replay = self.create_order(
            payload=self.order_payload(),
            key=key,
        )

        self.assertEqual(replay.status_code, 409)
        order.refresh_from_db()
        self.assertIsNotNone(order.access_token_revoked_at)


@override_settings(
    PAYSTACK_MODE="test",
    PAYSTACK_SECRET_KEY="sk_test_unit_mock",
    PAYSTACK_CALLBACK_URL="https://example.test/dic/payment/return",
    PAYSTACK_HTTP_TIMEOUT_SECONDS=10,
)
class PaymentApiTests(APITestCase):
    def setUp(self):
        today = timezone.localdate()
        camp_start = today + timedelta(days=30)
        self.edition = CampEdition.objects.create(
            name="Payment Test Camp",
            year=today.year,
            camp_start_date=camp_start,
            camp_end_date=camp_start + timedelta(days=6),
            registration_open_date=today - timedelta(days=1),
            registration_close_date=today + timedelta(days=1),
            registration_status=CampEdition.RegistrationStatus.OPEN,
            is_active=True,
        )
        self.category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Payment Test Category",
            fee_ngn=Decimal("12500.25"),
        )
        payload = {
            "primary_registrant": {
                "full_name": "Primary Registrant",
                "phone": "+233200000001",
                "email": "registrant@example.test",
            },
            "participants": [
                {
                    "category_id": self.category.pk,
                    "full_name": "Test Participant",
                    "address": "Test Address",
                    "phone": "+233200000000",
                    "email": "participant@example.test",
                    "date_of_birth": date(today.year - 20, 1, 1).isoformat(),
                    "sex": Participant.Sex.MALE,
                    "height_cm": "175",
                    "weight_kg": "70",
                    "academic_status": Participant.AcademicStatus.TERTIARY,
                    "occupation": Participant.Occupation.BUSINESS,
                    "marital_status": Participant.MaritalStatus.SINGLE,
                }
            ],
        }
        response = self.client.post(
            reverse("dic:order-create"),
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201)
        self.order_id = response.data["order_id"]
        self.access_token = response.data["access_token"]
        self.order = RegistrationOrder.objects.get(public_id=self.order_id)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}

    def initialize_url(self, order_id=None):
        return reverse(
            "dic:payment-initialize",
            args=[order_id or self.order_id],
        )

    def verify_url(self, reference, order_id=None):
        return reverse(
            "dic:payment-verify",
            args=[order_id or self.order_id, reference],
        )

    def create_pending_attempt(self, reference="DIC-payment-reference"):
        return PaymentAttempt.objects.create(
            order=self.order,
            reference=reference,
            amount_kobo=1_250_025,
            status=PaymentAttempt.Status.PENDING,
            authorization_url="https://checkout.paystack.com/test-access-code",
        )

    def provider_result(self, expected_reference, **overrides):
        result = {
            "id": 987654,
            "reference": expected_reference,
            "amount": 1_250_025,
            "currency": "NGN",
            "status": "success",
        }
        result.update(overrides)
        return result

    def test_payment_init_calculates_kobo_from_order_snapshots(self):
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.initialize_transaction.side_effect = lambda **kwargs: {
                "authorization_url": "https://checkout.paystack.com/test-access-code",
                "reference": kwargs["reference"],
            }
            response = self.client.post(
                self.initialize_url(),
                {"amount_kobo": 1, "amount_ngn": "0.01"},
                format="json",
                **self.auth,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["amount_kobo"], 1_250_025)
        self.assertEqual(response.data["currency"], "NGN")
        self.assertEqual(
            provider.initialize_transaction.call_args.kwargs["email"],
            "registrant@example.test",
        )
        self.assertEqual(
            provider.initialize_transaction.call_args.kwargs["amount_kobo"],
            1_250_025,
        )
        attempt = PaymentAttempt.objects.get()
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(attempt.reference, response.data["payment_reference"])

    def test_payment_init_retry_reuses_existing_pending_attempt(self):
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.initialize_transaction.side_effect = lambda **kwargs: {
                "authorization_url": "https://checkout.paystack.com/test-access-code",
                "reference": kwargs["reference"],
            }
            first = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )
            second = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["idempotent_replay"])
        self.assertEqual(
            first.data["payment_reference"],
            second.data["payment_reference"],
        )
        provider.initialize_transaction.assert_called_once()
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_failed_payment_attempt_can_be_retried_with_new_reference(self):
        failed = self.create_pending_attempt()
        failed.status = PaymentAttempt.Status.FAILED
        failed.save(update_fields=("status",))
        self.order.payment_status = RegistrationOrder.PaymentStatus.FAILED
        self.order.save(update_fields=("payment_status",))

        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.initialize_transaction.side_effect = lambda **kwargs: {
                "authorization_url": "https://checkout.paystack.com/new-access-code",
                "reference": kwargs["reference"],
            }
            response = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["payment_reference"], failed.reference)
        self.assertEqual(PaymentAttempt.objects.count(), 2)

    def test_untrusted_checkout_url_is_not_returned_to_the_registrant(self):
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.initialize_transaction.side_effect = lambda **kwargs: {
                "authorization_url": "https://attacker.example/collect",
                "reference": kwargs["reference"],
            }
            response = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("payment_reference", response.data)
        self.assertEqual(
            PaymentAttempt.objects.get().status,
            PaymentAttempt.Status.INITIALIZATION_UNKNOWN,
        )

    def test_payment_endpoints_require_valid_order_access(self):
        response = self.client.post(self.initialize_url(), {}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

        attempt = self.create_pending_attempt()
        wrong_order = uuid.uuid4()
        unauthorized = self.client.post(
            self.verify_url(attempt.reference, str(wrong_order)),
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(unauthorized.status_code, 404)

    def test_missing_paystack_credentials_do_not_create_attempts(self):
        with self.settings(PAYSTACK_SECRET_KEY=""):
            response = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    def test_live_paystack_key_is_rejected(self):
        with self.settings(PAYSTACK_SECRET_KEY="sk_live_not_used"):
            response = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    def test_cancelled_or_paid_orders_cannot_start_payment(self):
        self.order.status = RegistrationOrder.Status.CANCELLED
        self.order.save(update_fields=("status",))
        response = self.client.post(
            self.initialize_url(),
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

        self.order.status = RegistrationOrder.Status.SUBMITTED
        self.order.payment_status = RegistrationOrder.PaymentStatus.PAID
        self.order.save(update_fields=("status", "payment_status"))
        already_paid = self.client.post(
            self.initialize_url(),
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(already_paid.status_code, 400)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    def test_successful_server_verification_marks_order_paid_once(self):
        attempt = self.create_pending_attempt()
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.verify_transaction.return_value = self.provider_result(
                attempt.reference
            )
            response = self.client.post(
                self.verify_url(attempt.reference),
                {},
                format="json",
                **self.auth,
            )
            repeated = self.client.post(
                self.verify_url(attempt.reference),
                {},
                format="json",
                **self.auth,
            )

        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        self.assertEqual(self.order.status, RegistrationOrder.Status.CONFIRMED)
        self.assertTrue(repeated.data["idempotent_replay"])
        provider.verify_transaction.assert_called_once_with(attempt.reference)

    def test_failed_and_pending_provider_results_do_not_mark_order_paid(self):
        attempt = self.create_pending_attempt()
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.verify_transaction.return_value = self.provider_result(
                attempt.reference,
                status="pending",
            )
            pending = self.client.post(
                self.verify_url(attempt.reference),
                {},
                format="json",
                **self.auth,
            )
            provider.verify_transaction.return_value = self.provider_result(
                attempt.reference,
                status="failed",
            )
            failed = self.client.post(
                self.verify_url(attempt.reference),
                {},
                format="json",
                **self.auth,
            )

        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(pending.data["attempt_status"], PaymentAttempt.Status.PENDING)
        self.assertEqual(failed.data["attempt_status"], PaymentAttempt.Status.FAILED)
        self.assertEqual(attempt.provider_transaction_id, "987654")
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.FAILED)
        self.assertNotEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PAID)

    def test_mismatched_reference_amount_or_currency_never_settles_order(self):
        for index, mismatch in enumerate(
            (
                {"reference": "another-reference"},
                {"amount": 1},
                {"currency": "USD"},
            )
        ):
            attempt = self.create_pending_attempt(f"DIC-mismatch-{index}")
            with patch("dic.payment_views.PaystackClient") as client_factory:
                client_factory.return_value.verify_transaction.return_value = (
                    self.provider_result(attempt.reference, **mismatch)
                )
                response = self.client.post(
                    self.verify_url(attempt.reference),
                    {},
                    format="json",
                    **self.auth,
                )
            attempt.refresh_from_db()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(attempt.status, PaymentAttempt.Status.AMOUNT_MISMATCH)
            self.assertEqual(
                RegistrationOrder.objects.get(pk=self.order.pk).payment_status,
                RegistrationOrder.PaymentStatus.PENDING,
            )
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.save(update_fields=("status",))

    def test_provider_transaction_cannot_credit_a_second_attempt(self):
        first = self.create_pending_attempt("DIC-first-success")
        with patch("dic.payment_views.PaystackClient") as client_factory:
            client_factory.return_value.verify_transaction.return_value = (
                self.provider_result(first.reference)
            )
            settled = self.client.post(
                self.verify_url(first.reference),
                {},
                format="json",
                **self.auth,
            )
        self.assertEqual(settled.data["attempt_status"], PaymentAttempt.Status.SUCCESSFUL)

        second = self.create_pending_attempt("DIC-reused-provider-transaction")
        with patch("dic.payment_views.PaystackClient") as client_factory:
            client_factory.return_value.verify_transaction.return_value = (
                self.provider_result(second.reference)
            )
            response = self.client.post(
                self.verify_url(second.reference),
                {},
                format="json",
                **self.auth,
            )

        second.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(second.status, PaymentAttempt.Status.AMOUNT_MISMATCH)
        self.assertEqual(second.failure_code, "provider_transaction_reused")
        self.assertIsNone(second.provider_transaction_id)

    def test_unknown_initialization_cannot_create_a_duplicate_attempt(self):
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.initialize_transaction.side_effect = [
                PaystackTransportError("network simulation"),
            ]
            response = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )
            retry = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(retry.status_code, 400)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(
            PaymentAttempt.objects.get().status,
            PaymentAttempt.Status.INITIALIZATION_UNKNOWN,
        )

    def test_webhook_rejects_invalid_signature_and_verifies_success_once(self):
        attempt = self.create_pending_attempt()
        payload = {
            "event": "charge.success",
            "data": {"reference": attempt.reference},
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        webhook_url = reverse("dic:paystack-webhook")

        invalid = self.client.post(
            webhook_url,
            body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="invalid",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(PaystackWebhookEvent.objects.count(), 0)

        signature = hmac.new(
            b"sk_test_unit_mock",
            body,
            hashlib.sha512,
        ).hexdigest()
        with patch("dic.payment_views.PaystackClient") as client_factory:
            provider = client_factory.return_value
            provider.secret_key = "sk_test_unit_mock"
            provider.verify_transaction.return_value = self.provider_result(
                attempt.reference
            )
            first = self.client.post(
                webhook_url,
                body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=signature,
            )
            duplicate = self.client.post(
                webhook_url,
                body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=signature,
            )

        attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        self.assertEqual(PaystackWebhookEvent.objects.count(), 1)
        provider.verify_transaction.assert_called_once_with(attempt.reference)

    def test_non_success_webhook_is_audited_without_marking_order_paid(self):
        attempt = self.create_pending_attempt()
        body = json.dumps(
            {"event": "charge.failed", "data": {"reference": attempt.reference}},
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            b"sk_test_unit_mock",
            body,
            hashlib.sha512,
        ).hexdigest()
        with patch("dic.payment_views.PaystackClient") as client_factory:
            client_factory.return_value.secret_key = "sk_test_unit_mock"
            response = self.client.post(
                reverse("dic:paystack-webhook"),
                body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=signature,
            )

        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PENDING)
        self.assertEqual(
            PaystackWebhookEvent.objects.get().processing_status,
            PaystackWebhookEvent.ProcessingStatus.IGNORED,
        )


class ConcurrentPaymentSettlementTests(TransactionTestCase):
    def test_concurrent_verification_settles_one_attempt_once(self):
        today = timezone.localdate()
        camp_start = today + timedelta(days=30)
        edition = CampEdition.objects.create(
            name="Concurrent Payment Camp",
            year=today.year,
            camp_start_date=camp_start,
            camp_end_date=camp_start + timedelta(days=6),
            registration_open_date=today - timedelta(days=1),
            registration_close_date=today + timedelta(days=1),
            registration_status=CampEdition.RegistrationStatus.OPEN,
            is_active=True,
        )
        registrant = PrimaryRegistrant.objects.create(
            full_name="Concurrent Registrant",
            email="concurrent@example.test",
        )
        order = RegistrationOrder.objects.create(
            primary_registrant=registrant,
            edition=edition,
            idempotency_key_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            request_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            access_token_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        )
        attempt = PaymentAttempt.objects.create(
            order=order,
            reference="DIC-concurrent-reference",
            amount_kobo=10_000,
            status=PaymentAttempt.Status.PENDING,
        )
        provider_data = {
            "id": 987654,
            "reference": attempt.reference,
            "amount": 10_000,
            "currency": "NGN",
            "status": "success",
        }

        def settle():
            from django.db import close_old_connections

            close_old_connections()
            try:
                return _apply_verified_transaction(attempt.pk, provider_data)[0].status
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: settle(), range(2)))

        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(
            order.payment_status,
            RegistrationOrder.PaymentStatus.PAID,
        )
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        self.assertEqual(results.count(PaymentAttempt.Status.SUCCESSFUL), 2)


@override_settings(
    PAYSTACK_MODE="test",
    PAYSTACK_SECRET_KEY="sk_test_unit_mock",
    PAYSTACK_CALLBACK_URL="https://example.test/dic/payment/return",
    PAYSTACK_HTTP_TIMEOUT_SECONDS=10,
)
class PaystackClientTests(SimpleTestCase):
    @patch("dic.payments.urlopen")
    def test_initialization_uses_paystack_api_ngn_and_server_values(self, urlopen_mock):
        response = json.dumps(
            {
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/access",
                    "reference": "DIC-reference",
                },
            }
        ).encode("utf-8")
        urlopen_mock.return_value.__enter__.return_value.read.return_value = response

        client = PaystackClient()
        result = client.initialize_transaction(
            email="participant@example.test",
            amount_kobo=12345,
            reference="DIC-reference",
            callback_url="https://example.test/dic/payment/return",
            metadata={"order_id": "order-public-id"},
        )

        request = urlopen_mock.call_args.args[0]
        request_body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.paystack.co/transaction/initialize")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk_test_unit_mock")
        self.assertEqual(urlopen_mock.call_args.kwargs["timeout"], 10)
        self.assertEqual(request_body["amount"], 12345)
        self.assertEqual(request_body["currency"], "NGN")
        self.assertEqual(request_body["reference"], "DIC-reference")
        self.assertEqual(result["reference"], "DIC-reference")

    @patch("dic.payments.urlopen")
    def test_verification_escapes_reference_and_returns_provider_data(self, urlopen_mock):
        provider_data = {
            "status": "success",
            "reference": "DIC/reference",
            "amount": 100,
            "currency": "NGN",
        }
        urlopen_mock.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"status": True, "data": provider_data}
        ).encode("utf-8")

        result = PaystackClient().verify_transaction("DIC/reference")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.paystack.co/transaction/verify/DIC%2Freference",
        )
        self.assertEqual(request.method, "GET")
        self.assertEqual(result, provider_data)
