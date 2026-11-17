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
        self.assertEqual(data['source']['expected_timetable_total'], 180)
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

    def test_activation_preflight_is_read_only_and_reports_missing_gates(self):
        from django.test import override_settings
        self.client.force_login(self.owner)
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=0):
            response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        status = response.json()['housing_activation']
        self.assertFalse(status['ready'])
        self.assertEqual(status['mode'], 'read_only')
        self.assertIn('Housing automation actor is not configured.', status['blockers'])
        self.assertIn('Select the balanced housing strategy.', status['blockers'])
        self.assertFalse(DICAdminAuditEvent.objects.exists())
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.allocation_strategy, 'disabled')

    def test_activation_preflight_checks_actor_permissions_without_writes(self):
        from django.test import override_settings
        from .management.commands.initialize_dic2026_release import initialize
        from .allocation import allocation_configuration_fingerprint
        from django.utils import timezone
        initialize(self.edition, self.owner)
        self.edition.refresh_from_db()
        self.edition.allocation_strategy = 'balanced'
        self.edition.allocation_strategy_approved_at = timezone.now()
        self.edition.allocation_strategy_approved_by = self.owner
        self.edition.allocation_strategy_approval_note = 'Reviewed configuration.'
        self.edition.save()
        self.edition.allocation_approved_configuration = allocation_configuration_fingerprint(self.edition)
        self.edition.save(update_fields=['allocation_approved_configuration'])
        actor = get_user_model().objects.create_user(
            username='housing-unprivileged-actor', is_staff=True, password='synthetic')
        self.client.force_login(self.owner)
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=actor.pk):
            data = self.client.get(self.path).json()
        self.assertFalse(data['housing_activation']['ready'])
        self.assertTrue(any('lacks can_process_housing_queue' in x for x in data['housing_activation']['blockers']))
        self.assertFalse(data['housing_activation']['blockers'] == [])

    def test_activation_preflight_ready_only_with_current_approval_and_authorized_actor(self):
        from django.test import override_settings
        from .management.commands.initialize_dic2026_release import initialize
        from .allocation import allocation_configuration_fingerprint
        from django.utils import timezone
        initialize(self.edition, self.owner)
        self.edition.refresh_from_db()
        self.edition.allocation_strategy = 'balanced'
        self.edition.allocation_strategy_approved_at = timezone.now()
        self.edition.allocation_strategy_approved_by = self.owner
        self.edition.allocation_strategy_approval_note = 'Committee housing approval.'
        self.edition.save()
        self.edition.allocation_approved_configuration = allocation_configuration_fingerprint(self.edition)
        self.edition.save(update_fields=['allocation_approved_configuration'])
        self.client.force_login(self.owner)
        with override_settings(DAWANA_WEBSITE_ONLY=False, DIC_AUTOMATION_ACTOR_ID=self.owner.pk):
            ready = self.client.get(self.path).json()['housing_activation']
        self.assertTrue(ready['ready'], ready['blockers'])
        self.assertEqual(ready['blockers'], [])
        self.assertEqual(House.objects.filter(edition=self.edition).count(), 8)
