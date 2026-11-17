"""Production inspection endpoint is read-only and reserved to Django superusers."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import CampEdition, House, TimetableEntry, DICAdminAuditEvent


class ProductionInspectionTests(TestCase):
    def setUp(self):
        self.path = reverse('dic2026_production_inspection')
        self.edition = CampEdition.objects.create(
            name='DIC 2026', year=2026,
            camp_start_date=date(2026, 12, 23),
            camp_end_date=date(2027, 1, 1),
        )
        self.owner = get_user_model().objects.create_superuser(
            username='dic-2026-inspection-superuser',
            email='inspection@example.test', password='synthetic')
        self.staff = get_user_model().objects.create_user(
            username='dic-2026-inspection-staff', password='synthetic', is_staff=True)

    def test_anonymous_and_non_superuser_cannot_read_production_inventory(self):
        response = self.client.get(self.path)
        self.assertNotEqual(response.status_code, 200)
        self.client.force_login(self.staff)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('database', response.content.decode('utf-8'))

    def test_inspection_is_read_only_and_includes_exact_edition_and_source(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(data['mode'], 'read_only_no_database_changes')
        self.assertEqual(data['edition']['id'], self.edition.pk)
        self.assertEqual(data['edition']['camp_start'], '2026-12-23')
        self.assertEqual(data['edition']['camp_end'], '2027-01-01')
        self.assertEqual(data['houses'], [])
        self.assertEqual(data['timetables']['total'], 0)
        self.assertEqual(data['source']['expected_houses'], 8)
        self.assertEqual(data['source']['expected_timetable_total'], 182)
        self.assertEqual(data['source']['expected_food'], 27)
        self.assertTrue(data['ready_for_population_review'])
        self.assertEqual(House.objects.count(), 0)
        self.assertEqual(TimetableEntry.objects.count(), 0)
        self.assertFalse(DICAdminAuditEvent.objects.exists())
        self.edition.refresh_from_db()
        self.assertIsNone(self.edition.housing_age_reference_date)

    def test_conflicting_existing_house_is_reported_without_modification(self):
        house = House.objects.create(
            edition=self.edition, name='Unapproved existing house',
            gender='male', capacity=30)
        self.client.force_login(self.owner)
        data = self.client.get(self.path).json()
        self.assertFalse(data['ready_for_population_review'])
        self.assertTrue(data['issues'])
        house.refresh_from_db()
        self.assertEqual(house.name, 'Unapproved existing house')
        self.assertEqual(House.objects.count(), 1)

    def test_post_does_not_start_population(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.path, data={})
        self.assertEqual(response.status_code, 405)
        self.assertFalse(House.objects.exists())
        self.assertFalse(TimetableEntry.objects.exists())
