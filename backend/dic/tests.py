import uuid
import hashlib
import hmac
import json
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
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
    RegistrationOrderPriceItem,
    RegistrationOrderPriceRevision,
)
from .payment_views import _apply_verified_transaction
from .payments import PaystackClient, PaystackTransportError
from .pricing import current_order_prices, sign_repricing_quote
from .security import digest_value, new_order_access_token, order_access_token_expiry


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

    def test_google_maps_place_identifier_rejects_invalid_characters(self):
        edition = self.make_edition(
            venue_google_place_id="not a valid place id",
        )

        with self.assertRaises(ValidationError) as raised:
            edition.full_clean()

        self.assertIn("venue_google_place_id", raised.exception.message_dict)


class Dic2026SetupCommandTests(TestCase):
    def test_creates_confirmed_details_as_a_closed_draft_without_categories(self):
        call_command("setup_dic_2026")
        edition = CampEdition.objects.get(year=2026)

        self.assertEqual(edition.camp_start_date, date(2026, 12, 23))
        self.assertEqual(edition.camp_end_date, date(2027, 1, 1))
        self.assertEqual(edition.venue_name, "Faisal Omar Memorial School")
        self.assertTrue(edition.is_active)
        self.assertEqual(edition.registration_status, CampEdition.RegistrationStatus.DRAFT)
        self.assertIsNone(edition.registration_open_date)
        self.assertIsNone(edition.registration_close_date)
        self.assertIsNone(edition.early_bird_cutoff_at)
        self.assertEqual(edition.registration_categories.count(), 0)

    def test_rerun_does_not_overwrite_existing_edition_configuration(self):
        call_command("setup_dic_2026")
        edition = CampEdition.objects.get(year=2026)
        edition.general_information = {"committee_note": "preserve"}
        edition.save(update_fields=("general_information",))

        call_command("setup_dic_2026")

        edition.refresh_from_db()
        self.assertEqual(edition.general_information, {"committee_note": "preserve"})
        self.assertEqual(CampEdition.objects.filter(year=2026).count(), 1)

    def test_does_not_displace_an_existing_active_edition(self):
        CampEdition.objects.create(
            name="Other Active Camp",
            year=2025,
            camp_start_date=date(2025, 12, 1),
            camp_end_date=date(2025, 12, 7),
            is_active=True,
        )

        with self.assertRaises(CommandError):
            call_command("setup_dic_2026")

        self.assertFalse(CampEdition.objects.filter(year=2026).exists())


class CampEditionAdminTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(
            name="Daarul Islam Camp 2026",
            year=2026,
            camp_start_date=date(2026, 12, 23),
            camp_end_date=date(2027, 1, 1),
            is_active=True,
            registration_status=CampEdition.RegistrationStatus.DRAFT,
        )
        self.admin_instance = admin.site._registry[CampEdition]
        self.request = RequestFactory().post("/admin/dic/campedition/")
        self.user = get_user_model().objects.create_superuser(
            username="config-admin",
            email="config-admin@example.test",
            password="not-a-real-password",
        )
        self.request.user = self.user
        self.today = today

    def test_confirmed_details_require_the_dedicated_admin_permission(self):
        regular_user = get_user_model().objects.create_user(
            username="regular-admin",
            password="not-a-real-password",
            is_staff=True,
        )
        self.request.user = regular_user
        readonly = self.admin_instance.get_readonly_fields(
            self.request,
            self.edition,
        )
        self.assertIn("year", readonly)
        self.assertIn("camp_start_date", readonly)
        self.assertIn("camp_end_date", readonly)
        self.assertIn("venue_name", readonly)

        permission = self.edition._meta.permissions[0][0]
        from django.contrib.auth.models import Permission

        can_edit = Permission.objects.get(
            content_type__app_label="dic",
            codename=permission,
        )
        regular_user.user_permissions.add(can_edit)
        regular_user = get_user_model().objects.get(pk=regular_user.pk)
        self.request.user = regular_user
        readonly = self.admin_instance.get_readonly_fields(
            self.request,
            self.edition,
        )
        self.assertNotIn("year", readonly)
        self.assertNotIn("camp_start_date", readonly)
        self.assertNotIn("camp_end_date", readonly)
        self.assertNotIn("venue_name", readonly)

    def test_incomplete_pricing_cannot_open_registration(self):
        self.edition.registration_status = CampEdition.RegistrationStatus.OPEN

        with self.assertRaises(ValidationError):
            self.admin_instance.save_model(
                self.request,
                self.edition,
                form=None,
                change=True,
            )

        self.edition.refresh_from_db()
        self.assertEqual(
            self.edition.registration_status,
            CampEdition.RegistrationStatus.DRAFT,
        )

    def test_complete_regular_pricing_allows_an_authorized_admin_to_open(self):
        self.edition.registration_open_date = self.today
        self.edition.registration_close_date = self.today + timedelta(days=2)
        self.edition.registration_status = CampEdition.RegistrationStatus.OPEN
        RegistrationCategory.objects.create(
            edition=self.edition,
            name="Committee-approved test category",
            fee_ngn=Decimal("100.00"),
        )

        self.admin_instance.save_model(
            self.request,
            self.edition,
            form=None,
            change=True,
        )

        self.edition.refresh_from_db()
        self.assertEqual(
            self.edition.registration_status,
            CampEdition.RegistrationStatus.OPEN,
        )


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

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["year"], self.edition.year)
        self.assertTrue(response.data["registration_is_open"])
        category_ids = {item["id"] for item in response.data["categories"]}
        self.assertEqual(category_ids, {self.category.pk, self.other_category.pk})
        self.assertNotIn(inactive.pk, category_ids)

    def test_edition_details_changed_in_admin_are_returned_by_public_api(self):
        registration_open = self.edition.registration_open_date
        registration_close = self.edition.registration_close_date
        self.edition.year = 2026
        self.edition.camp_start_date = date(2026, 12, 23)
        self.edition.camp_end_date = date(2027, 1, 1)
        self.edition.venue_name = "Faisal Omar Memorial School"
        self.edition.venue_directions_address = ""
        self.edition.venue_directions_verified = False
        user = get_user_model().objects.create_superuser(
            username="dic-admin",
            email="dic-admin@example.test",
            password="not-a-real-password",
        )
        request = RequestFactory().post("/admin/dic/campedition/")
        request.user = user
        admin.site._registry[CampEdition].save_model(
            request,
            self.edition,
            form=None,
            change=True,
        )

        response = self.client.get(reverse("dic:registration-options"))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["camp_start_date"], "2026-12-23")
        self.assertEqual(response.data["camp_end_date"], "2027-01-01")
        self.assertEqual(response.data["venue"], "Faisal Omar Memorial School")
        self.assertIsNone(response.data["venue_directions_url"])
        self.assertEqual(response.data["registration_open_date"], registration_open.isoformat())
        self.assertEqual(response.data["registration_close_date"], registration_close.isoformat())

    def test_verified_directions_are_returned_only_with_a_destination(self):
        self.edition.venue_name = "Faisal Omar Memorial School"
        self.edition.venue_directions_verified = True
        self.edition.save()

        without_destination = self.client.get(reverse("dic:registration-options"))
        self.assertIsNone(without_destination.data["venue_directions_url"])

        user = get_user_model().objects.create_user(
            username="venue-verifier",
            password="not-a-real-password",
        )
        self.edition.venue_directions_address = "Verified test destination"
        self.edition.venue_directions_verified_at = timezone.now()
        self.edition.venue_directions_verified_by = user
        self.edition.save()

        with_destination = self.client.get(reverse("dic:registration-options"))
        self.assertIn(
            "destination=Verified%20test%20destination",
            with_destination.data["venue_directions_url"],
        )

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

    def test_early_bird_is_selected_before_cutoff_and_regular_at_or_after(self):
        cutoff = datetime.combine(
            self.today,
            datetime.min.time(),
        ).replace(hour=12, tzinfo=ZoneInfo("Africa/Lagos"))
        self.edition.early_bird_cutoff_at = cutoff
        self.edition.save(update_fields=("early_bird_cutoff_at",))
        self.category.early_bird_fee_ngn = Decimal("10000.00")
        self.category.save(update_fields=("early_bird_fee_ngn",))
        self.other_category.early_bird_fee_ngn = Decimal("7000.00")
        self.other_category.save(update_fields=("early_bird_fee_ngn",))

        cases = (
            (cutoff - timedelta(seconds=1), "10000.00", "early_bird"),
            (cutoff, "12500.25", "regular"),
            (cutoff + timedelta(seconds=1), "12500.25", "regular"),
        )
        for when, expected_fee, expected_type in cases:
            with patch("dic.views.timezone.now", return_value=when):
                response = self.create_order()
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data["total_amount_ngn"], expected_fee)
            order = RegistrationOrder.objects.get(
                public_id=response.data["order_id"]
            )
            price_item = order.current_price_revision.items.get()
            self.assertEqual(price_item.fee_snapshot_ngn, Decimal(expected_fee))
            self.assertEqual(price_item.price_type, expected_type)

    def test_incomplete_category_pricing_keeps_registration_closed(self):
        self.category.fee_ngn = None
        self.category.save(update_fields=("fee_ngn",))

        options = self.client.get(reverse("dic:registration-options"))
        order = self.create_order()

        self.assertFalse(options.data["registration_is_open"])
        self.assertIsNone(options.data["categories"][0]["current_fee_ngn"])
        self.assertEqual(order.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 0)

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
        self.order_payload = payload
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
            amount_kobo=int(Decimal(self.order.total_amount_ngn) * 100),
            status=PaymentAttempt.Status.PENDING,
            authorization_url="https://checkout.paystack.com/test-access-code",
            price_revision=self.order.current_price_revision,
        )

    def provider_result(self, expected_reference, **overrides):
        attempt = PaymentAttempt.objects.filter(reference=expected_reference).first()
        result = {
            "id": 987654,
            "reference": expected_reference,
            "amount": (
                attempt.amount_kobo
                if attempt
                else int(Decimal(self.order.total_amount_ngn) * 100)
            ),
            "currency": "NGN",
            "status": "success",
            "paid_at": timezone.now().isoformat(),
        }
        result.update(overrides)
        return result

    def create_early_bird_order(self):
        cutoff = timezone.now() + timedelta(seconds=30)
        self.edition.early_bird_cutoff_at = cutoff
        self.edition.save(update_fields=("early_bird_cutoff_at",))
        self.category.early_bird_fee_ngn = Decimal("10000.00")
        self.category.save(update_fields=("early_bird_fee_ngn",))
        response = self.client.post(
            reverse("dic:order-create"),
            self.order_payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201)
        self.order_id = response.data["order_id"]
        self.access_token = response.data["access_token"]
        self.order = RegistrationOrder.objects.get(public_id=self.order_id)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}
        self.assertEqual(self.order.access_token_digest, hashlib.sha256(self.access_token.encode()).hexdigest())
        self.assertTrue(self.auth["HTTP_AUTHORIZATION"].startswith("Bearer "))
        self.assertEqual(
            self.order.access_token_digest,
            hashlib.sha256(
                self.auth["HTTP_AUTHORIZATION"].partition(" ")[2].encode()
            ).hexdigest(),
        )
        return cutoff

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

    def test_provider_confirmed_pre_cutoff_payment_settles_after_cutoff(self):
        cutoff = self.create_early_bird_order()
        attempt = self.create_pending_attempt()
        paid_at = cutoff - timedelta(seconds=1)
        with patch("dic.payment_views.timezone.now", return_value=cutoff + timedelta(seconds=1)):
            with patch("dic.payment_views.PaystackClient") as client_factory:
                client_factory.return_value.verify_transaction.return_value = (
                    self.provider_result(
                        attempt.reference,
                        paid_at=paid_at.isoformat(),
                    )
                )
                response = self.client.post(
                    self.verify_url(attempt.reference),
                    {},
                    format="json",
                    **self.auth,
                )

        attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        self.assertEqual(attempt.provider_paid_at, paid_at)
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        self.assertEqual(self.order.total_amount_ngn, Decimal("10000.00"))

    def test_early_bird_payment_at_or_after_cutoff_requires_reconciliation(self):
        cutoff = self.create_early_bird_order()
        for index, paid_at in enumerate(
            (cutoff, cutoff + timedelta(seconds=1))
        ):
            attempt = self.create_pending_attempt(f"DIC-late-early-{index}")
            with patch("dic.payment_views.PaystackClient") as client_factory:
                client_factory.return_value.verify_transaction.return_value = (
                    self.provider_result(
                        attempt.reference,
                        id=987654 + index,
                        paid_at=paid_at.isoformat(),
                    )
                )
                response = self.client.post(
                    self.verify_url(attempt.reference),
                    {},
                    format="json",
                    **self.auth,
                )
            attempt.refresh_from_db()
            self.order.refresh_from_db()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempt.status,
                PaymentAttempt.Status.RECONCILIATION_REQUIRED,
            )
            self.assertEqual(
                self.order.payment_status,
                RegistrationOrder.PaymentStatus.PENDING,
            )
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.save(update_fields=("status",))

    def test_missing_provider_paid_at_requires_reconciliation(self):
        for index, paid_at in enumerate((None, "not-a-provider-timestamp")):
            attempt = self.create_pending_attempt(f"DIC-invalid-paid-at-{index}")
            with patch("dic.payment_views.PaystackClient") as client_factory:
                client_factory.return_value.verify_transaction.return_value = (
                    self.provider_result(
                        attempt.reference,
                        id=987654 + index,
                        paid_at=paid_at,
                    )
                )
                response = self.client.post(
                    self.verify_url(attempt.reference),
                    {},
                    format="json",
                    **self.auth,
                )

            attempt.refresh_from_db()
            self.order.refresh_from_db()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempt.status,
                PaymentAttempt.Status.RECONCILIATION_REQUIRED,
            )
            self.assertEqual(
                attempt.failure_code,
                "provider_paid_at_missing_or_invalid",
            )
            self.assertEqual(
                self.order.payment_status,
                RegistrationOrder.PaymentStatus.PENDING,
            )
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.save(update_fields=("status",))

    def test_cutoff_crossing_requires_acceptance_and_rejects_late_old_authorization(self):
        cutoff = self.create_early_bird_order()
        old_attempt = self.create_pending_attempt("DIC-old-early-authorization")
        time_after_cutoff = cutoff + timedelta(seconds=1)
        with patch("dic.payment_views.timezone.now", return_value=time_after_cutoff):
            stale = self.client.post(
                self.initialize_url(),
                {},
                format="json",
                **self.auth,
            )
        self.assertEqual(stale.status_code, 409, stale.data)
        self.assertTrue(stale.data["repricing_required"])
        self.assertEqual(stale.data["total_amount_ngn"], "12500.25")
        old_attempt.refresh_from_db()
        self.assertEqual(old_attempt.status, PaymentAttempt.Status.PENDING)

        with patch("dic.payment_views.timezone.now", return_value=time_after_cutoff):
            accepted = self.client.post(
                reverse("dic:pricing-accept", args=[self.order_id]),
                {"quote": stale.data["quote"]},
                format="json",
                **self.auth,
            )
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.data["accepted"])
        self.assertEqual(accepted.data["total_amount_ngn"], "12500.25")
        old_attempt.refresh_from_db()
        self.assertEqual(old_attempt.status, PaymentAttempt.Status.SUPERSEDED)

        with patch("dic.payment_views.PaystackClient") as client_factory:
            client_factory.return_value.verify_transaction.return_value = (
                self.provider_result(
                    old_attempt.reference,
                    paid_at=time_after_cutoff.isoformat(),
                )
            )
            result = self.client.post(
                self.verify_url(old_attempt.reference),
                {},
                format="json",
                **self.auth,
            )
        old_attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            old_attempt.status,
            PaymentAttempt.Status.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(
            old_attempt.failure_code,
            "superseded_quote_paid",
        )
        self.assertEqual(
            self.order.payment_status,
            RegistrationOrder.PaymentStatus.PENDING,
        )

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

    def test_delayed_webhook_honors_verified_pre_cutoff_completion_time(self):
        cutoff = self.create_early_bird_order()
        attempt = self.create_pending_attempt("DIC-delayed-early-payment")
        body = json.dumps(
            {
                "event": "charge.success",
                "data": {"reference": attempt.reference},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            b"sk_test_unit_mock",
            body,
            hashlib.sha512,
        ).hexdigest()
        with patch("dic.payment_views.timezone.now", return_value=cutoff + timedelta(seconds=2)):
            with patch("dic.payment_views.PaystackClient") as client_factory:
                provider = client_factory.return_value
                provider.secret_key = "sk_test_unit_mock"
                provider.verify_transaction.return_value = self.provider_result(
                    attempt.reference,
                    paid_at=(cutoff - timedelta(seconds=1)).isoformat(),
                )
                response = self.client.post(
                    reverse("dic:paystack-webhook"),
                    body,
                    content_type="application/json",
                    HTTP_X_PAYSTACK_SIGNATURE=signature,
                )

        attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        self.assertEqual(self.order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        self.assertEqual(self.order.total_amount_ngn, Decimal("10000.00"))

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
        category = RegistrationCategory.objects.create(
            edition=edition,
            name="Concurrent Category",
            fee_ngn=Decimal("100.00"),
        )
        participant = Participant.objects.create(
            full_name="Concurrent Participant",
            address="Test Address",
            phone="+233200000002",
            email="concurrent-participant@example.test",
            date_of_birth=date(today.year - 20, 1, 1),
            sex=Participant.Sex.MALE,
            height_cm=Decimal("175.00"),
            weight_kg=Decimal("70.00"),
            academic_status=Participant.AcademicStatus.TERTIARY,
            occupation=Participant.Occupation.BUSINESS,
            marital_status=Participant.MaritalStatus.SINGLE,
        )
        order_item = RegistrationOrderItem.objects.create(
            order=order,
            participant=participant,
            category=category,
            fee_snapshot_ngn=Decimal("100.00"),
        )
        revision = RegistrationOrderPriceRevision.objects.create(
            order=order,
            revision_number=1,
            total_amount_ngn=Decimal("100.00"),
            accepted_at=timezone.now(),
        )
        RegistrationOrderPriceItem.objects.create(
            revision=revision,
            order_item=order_item,
            category_name_snapshot=category.name,
            regular_fee_snapshot_ngn=Decimal("100.00"),
            fee_snapshot_ngn=Decimal("100.00"),
            price_type=RegistrationOrderPriceItem.PriceType.REGULAR,
        )
        order.current_price_revision = revision
        order.save(update_fields=("current_price_revision",))
        attempt = PaymentAttempt.objects.create(
            order=order,
            reference="DIC-concurrent-reference",
            amount_kobo=10_000,
            status=PaymentAttempt.Status.PENDING,
            price_revision=revision,
        )
        provider_data = {
            "id": 987654,
            "reference": attempt.reference,
            "amount": 10_000,
            "currency": "NGN",
            "status": "success",
            "paid_at": timezone.now().isoformat(),
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

    def test_concurrent_repricing_and_late_payment_fail_closed(self):
        from django.db import close_old_connections
        from rest_framework.test import APIClient

        today = timezone.localdate()
        cutoff = timezone.now() - timedelta(seconds=2)
        edition = CampEdition.objects.create(
            name="Concurrent Repricing Camp",
            year=today.year,
            camp_start_date=today + timedelta(days=30),
            camp_end_date=today + timedelta(days=36),
            early_bird_cutoff_at=cutoff,
        )
        category = RegistrationCategory.objects.create(
            edition=edition,
            name="Concurrent Repricing Category",
            fee_ngn=Decimal("200.00"),
            early_bird_fee_ngn=Decimal("100.00"),
        )
        registrant = PrimaryRegistrant.objects.create(
            full_name="Concurrent Repricing Registrant",
            email="repricing@example.test",
        )
        token = new_order_access_token()
        order = RegistrationOrder.objects.create(
            primary_registrant=registrant,
            edition=edition,
            idempotency_key_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            request_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            access_token_digest=digest_value(token),
            access_token_expires_at=order_access_token_expiry(),
        )
        participant = Participant.objects.create(
            full_name="Concurrent Repricing Participant",
            address="Test Address",
            phone="+233200000003",
            email="repricing-participant@example.test",
            date_of_birth=date(today.year - 20, 1, 1),
            sex=Participant.Sex.MALE,
            height_cm=Decimal("175.00"),
            weight_kg=Decimal("70.00"),
            academic_status=Participant.AcademicStatus.TERTIARY,
            occupation=Participant.Occupation.BUSINESS,
            marital_status=Participant.MaritalStatus.SINGLE,
        )
        order_item = RegistrationOrderItem.objects.create(
            order=order,
            participant=participant,
            category=category,
            fee_snapshot_ngn=Decimal("100.00"),
        )
        revision = RegistrationOrderPriceRevision.objects.create(
            order=order,
            revision_number=1,
            early_bird_cutoff_at=cutoff,
            total_amount_ngn=Decimal("100.00"),
            accepted_at=cutoff - timedelta(minutes=1),
        )
        RegistrationOrderPriceItem.objects.create(
            revision=revision,
            order_item=order_item,
            category_name_snapshot=category.name,
            early_bird_fee_snapshot_ngn=Decimal("100.00"),
            regular_fee_snapshot_ngn=Decimal("200.00"),
            fee_snapshot_ngn=Decimal("100.00"),
            price_type=RegistrationOrderPriceItem.PriceType.EARLY_BIRD,
        )
        order.current_price_revision = revision
        order.save(update_fields=("current_price_revision",))
        attempt = PaymentAttempt.objects.create(
            order=order,
            reference="DIC-concurrent-repricing-reference",
            amount_kobo=10_000,
            status=PaymentAttempt.Status.PENDING,
            price_revision=revision,
        )
        prices = current_order_prices(order, timezone.now())
        quote = sign_repricing_quote(order, prices)
        provider_data = {
            "id": 987655,
            "reference": attempt.reference,
            "amount": 10_000,
            "currency": "NGN",
            "status": "success",
            "paid_at": (cutoff + timedelta(seconds=1)).isoformat(),
        }
        barrier = threading.Barrier(2)

        def accept_repricing():
            close_old_connections()
            try:
                client = APIClient()
                barrier.wait()
                response = client.post(
                    reverse("dic:pricing-accept", args=[order.public_id]),
                    {"quote": quote},
                    format="json",
                    HTTP_AUTHORIZATION=f"Bearer {token}",
                )
                return response.status_code
            finally:
                close_old_connections()

        def verify_payment():
            close_old_connections()
            try:
                barrier.wait()
                return _apply_verified_transaction(attempt.pk, provider_data)[0].status
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            repricing_result, payment_result = list(
                executor.map(
                    lambda function: function(),
                    (accept_repricing, verify_payment),
                )
            )

        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertIn(repricing_result, (200, 400))
        self.assertEqual(payment_result, PaymentAttempt.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(
            order.payment_status,
            RegistrationOrder.PaymentStatus.PENDING,
        )
        self.assertIn(order.current_price_revision.revision_number, (1, 2))


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
