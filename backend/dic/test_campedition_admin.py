"""Exercise the real Admin POST lifecycle, rather than calling save_model alone."""
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import CampEdition, House, RegistrationCategory


class CampEditionAdminCreationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="camp-config-test", email="camp@example.test", password="test-only"
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:dic_campedition_add")

    def payload(self, **overrides):
        data = {
            "name": "Test camp", "year": "2098",
            "camp_start_date": "2098-12-23", "camp_end_date": "2099-01-01",
            "registration_open_date": "2098-10-01",
            "registration_close_date": "2098-12-20",
            "registration_status": "draft", "allocation_strategy": "disabled",
            "general_information": "{}",
            "registration_categories-TOTAL_FORMS": "0",
            "registration_categories-INITIAL_FORMS": "0",
            "houses-TOTAL_FORMS": "0", "houses-INITIAL_FORMS": "0",
            "_save": "Save",
        }
        data.update(overrides)
        return data

    def with_inlines(self, **overrides):
        return self.payload(**{
            "registration_categories-TOTAL_FORMS": "1",
            "registration_categories-0-name": "Test category",
            "registration_categories-0-fee_ngn": "100.00",
            "registration_categories-0-is_active": "on",
            "houses-TOTAL_FORMS": "1",
            "houses-0-name": "Test house", "houses-0-gender": "female",
            "houses-0-purpose": "participants", "houses-0-status": "active",
            **overrides,
        })

    def assert_not_saved(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CampEdition.objects.exists())
        self.assertFalse(RegistrationCategory.objects.exists())
        self.assertFalse(House.objects.exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_create_draft_without_inlines(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("admin:dic_campedition_changelist"))
        self.assertEqual(CampEdition.objects.get().registration_status, "draft")
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_create_draft_with_category_and_house(self):
        response = self.client.post(self.url, self.with_inlines())
        self.assertEqual(response.status_code, 302)
        edition = CampEdition.objects.get()
        self.assertEqual(edition.registration_categories.get().name, "Test category")
        self.assertIsNone(edition.houses.get().capacity)

    def test_confirmed_2026_creation_shows_form_error(self):
        response = self.client.post(self.url, self.with_inlines(year="2026"))
        self.assert_not_saved(response)
        self.assertIn("setup_dic_2026", str(response.context["adminform"].form.errors["year"]))

    def test_open_without_categories_shows_inline_error(self):
        response = self.client.post(self.url, self.payload(registration_status="open"))
        self.assert_not_saved(response)
        self.assertContains(response, "At least one active category")

    def test_create_open_with_submitted_category_and_house(self):
        response = self.client.post(self.url, self.with_inlines(registration_status="open"))
        self.assertEqual(response.status_code, 302)
        edition = CampEdition.objects.get()
        self.assertTrue(edition.pricing_configuration_is_complete)
        self.assertEqual(edition.houses.count(), 1)

    def test_create_open_with_early_bird_prices(self):
        response = self.client.post(self.url, self.with_inlines(**{
            "registration_status": "open",
            "registration_categories-0-early_bird_fee_ngn": "75.00",
            "early_bird_cutoff_at_0": "2098-11-01",
            "early_bird_cutoff_at_1": "12:00:00",
        }))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CampEdition.objects.get().pricing_configuration_is_complete)

    def test_duplicate_year_and_active_edition_are_form_errors(self):
        self.client.post(self.url, self.payload(is_active="on"))
        for overrides in ({}, {"year": "2097", "is_active": "on"}):
            with self.subTest(overrides=overrides):
                response = self.client.post(self.url, self.payload(**overrides))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertEqual(CampEdition.objects.count(), 1)

    def test_open_with_unpriced_or_inactive_category_is_rejected(self):
        for overrides in (
            {"registration_categories-0-fee_ngn": ""},
            {"registration_categories-0-fee_ngn": "0"},
            {"registration_categories-0-is_active": ""},
            {"registration_open_date": ""},
            {"early_bird_cutoff_at_0": "2098-11-01", "early_bird_cutoff_at_1": "12:00:00"},
        ):
            with self.subTest(overrides=overrides):
                response = self.client.post(self.url, self.with_inlines(
                    registration_status="open", **overrides
                ))
                self.assert_not_saved(response)

    def test_invalid_house_rejects_entire_submission(self):
        response = self.client.post(self.url, self.with_inlines(**{
            "houses-0-purpose": "fathers_admins", "houses-0-gender": "female",
        }))
        self.assert_not_saved(response)
        self.assertContains(response, "must be designated male")

    def test_invalid_dates_are_form_errors(self):
        response = self.client.post(self.url, self.payload(camp_end_date="2098-01-01"))
        self.assert_not_saved(response)
        self.assertIn("camp_end_date", response.context["adminform"].form.errors)

    def test_open_uses_inline_edits_and_deletions(self):
        self.client.post(self.url, self.with_inlines())
        edition = CampEdition.objects.get()
        category = edition.registration_categories.get()
        house = edition.houses.get()
        url = reverse("admin:dic_campedition_change", args=[edition.pk])
        data = self.with_inlines(**{
            "registration_status": "open",
            "registration_categories-INITIAL_FORMS": "1",
            "registration_categories-0-id": str(category.pk),
            "registration_categories-0-edition": str(edition.pk),
            "houses-INITIAL_FORMS": "1", "houses-0-id": str(house.pk),
            "houses-0-edition": str(edition.pk),
        })
        for overrides in (
            {"registration_categories-0-DELETE": "on"},
            {"registration_categories-0-fee_ngn": "0"},
            {"registration_categories-0-is_active": ""},
        ):
            with self.subTest(overrides=overrides):
                response = self.client.post(url, {**data, **overrides})
                self.assertEqual(response.status_code, 200)
                edition.refresh_from_db()
                category.refresh_from_db()
                self.assertEqual(edition.registration_status, "draft")
                self.assertEqual(category.fee_ngn, 100)
                self.assertTrue(category.is_active)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        edition.refresh_from_db()
        self.assertEqual(edition.registration_status, "open")

    def test_staff_without_category_permissions_gets_form_error(self):
        staff = get_user_model().objects.create_user(username="limited", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(
            content_type__app_label="dic", codename="add_campedition"
        ))
        self.client.force_login(staff)
        response = self.client.post(self.url, self.payload(registration_status="open"))
        self.assert_not_saved(response)
        self.assertIn("registration_status", response.context["adminform"].form.errors)

    def test_staff_without_category_permissions_can_open_configured_edition(self):
        self.client.post(self.url, self.with_inlines())
        edition = CampEdition.objects.get()
        staff = get_user_model().objects.create_user(username="edition-editor", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(
            content_type__app_label="dic", codename="change_campedition"
        ))
        self.client.force_login(staff)
        response = self.client.post(
            reverse("admin:dic_campedition_change", args=[edition.pk]),
            self.payload(registration_status="open"),
        )
        self.assertEqual(response.status_code, 302)
        edition.refresh_from_db()
        self.assertEqual(edition.registration_status, "open")
