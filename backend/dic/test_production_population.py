"""The Admin one-screen apply remains human-confirmed and safe."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import CampEdition, House, RegistrationOrder, TimetableEntry


class ProductionPopulationTests(TestCase):
    def setUp(self):
        self.path = reverse('dic2026_production_population')
        self.edition = CampEdition.objects.create(
            name='DIC 2026', year=2026,
            camp_start_date=date(2026, 12, 23),
            camp_end_date=date(2027, 1, 1),
        )
        self.owner = get_user_model().objects.create_superuser(
            username='production-population-owner',
            email='owner@example.test', password='synthetic')
        self.staff = get_user_model().objects.create_user(
            username='production-population-staff', password='synthetic', is_staff=True)

    def test_preview_and_unapproved_post_do_not_write(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, 'DIC 2026')
        self.assertFalse(House.objects.exists())
        self.assertFalse(TimetableEntry.objects.exists())
        self.assertEqual(self.client.post(self.path, {'confirmation': 'POPULATE DIC 2026'}).status_code, 200)
        self.assertFalse(House.objects.exists())
        self.assertFalse(TimetableEntry.objects.exists())

    def test_staff_and_unauthenticated_users_cannot_access(self):
        self.assertNotEqual(self.client.get(self.path).status_code, 200)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.assertEqual(self.client.post(self.path, {}).status_code, 403)

    def test_explicit_reviewed_apply_adds_approved_records_and_is_idempotent(self):
        from .management.commands.initialize_dic2026_release import SOURCE
        import hashlib
        from django.db import connection

        self.client.force_login(self.owner)
        payload = {
            'edition_id': str(self.edition.pk),
            'database_name': str(connection.settings_dict['NAME']),
            'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'confirmation': 'POPULATE DIC 2026',
        }
        result = self.client.post(self.path, payload)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Reference population finished')
        self.assertEqual(House.objects.filter(edition=self.edition).count(), 8)
        self.assertEqual(TimetableEntry.objects.filter(edition=self.edition).count(), 180)
        self.assertFalse(TimetableEntry.objects.filter(status='published').exists())
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.housing_age_reference_date, date(2026, 12, 23))
        again = self.client.post(self.path, payload)
        self.assertContains(again, 'Reference population finished')
        self.assertEqual(House.objects.filter(edition=self.edition).count(), 8)
        self.assertEqual(TimetableEntry.objects.filter(edition=self.edition).count(), 180)

    def test_conflicting_house_does_not_partially_write(self):
        from .management.commands.initialize_dic2026_release import SOURCE
        import hashlib
        from django.db import connection

        House.objects.create(edition=self.edition, name='Unknown house', gender='male', capacity=30)
        self.client.force_login(self.owner)
        payload = {
            'edition_id': str(self.edition.pk),
            'database_name': str(connection.settings_dict['NAME']),
            'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'confirmation': 'POPULATE DIC 2026',
        }
        response = self.client.post(self.path, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unmatched existing participant house')
        self.assertEqual(House.objects.count(), 1)
        self.assertFalse(TimetableEntry.objects.exists())
