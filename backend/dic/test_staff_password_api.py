"""Staff password change acceptance, synthetic users and disposable test DB only."""
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from dic.models import DICAdminAuditEvent


class StaffPasswordChangeTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.operator = self.User.objects.create_user(
            username='staff-pass-operations', password='OldStrongPassphrase-OnlyTest-33!',
            is_staff=True, is_active=True,
        )
        self.operator.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='can_view_dic_operations',
        ))
        self.client.force_login(self.operator)
        self.url = reverse('dic:staff-password-change')
        self.valid = dict(
            current_password='OldStrongPassphrase-OnlyTest-33!',
            new_password='River Lantern Library Sunset 2026!',
            confirm_password='River Lantern Library Sunset 2026!',
        )

    def test_staff_updates_own_password_preserves_session_and_roles(self):
        original_roles = set(self.operator.user_permissions.values_list('pk', flat=True))
        response = self.client.post(self.url, self.valid, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.check_password(self.valid['new_password']))
        self.assertIsNone(authenticate(username=self.operator.username, password=self.valid['current_password']))
        self.assertFalse(self.operator.is_superuser)
        self.assertEqual(original_roles, set(self.operator.user_permissions.values_list('pk', flat=True)))
        self.assertEqual(self.client.get(reverse('dic:operations-me')).status_code, 200)
        self.assertEqual(DICAdminAuditEvent.objects.filter(
            action='staff_password_changed', actor=self.operator,
        ).count(), 1)
        self.assertNotIn(self.valid['new_password'], str(DICAdminAuditEvent.objects.last().details))

    def test_wrong_current_mismatch_and_weak_password_rejected(self):
        for values in (
            {**self.valid, 'current_password': 'not-the-current-password'},
            {**self.valid, 'confirm_password': 'Different Passphrase'},
            {**self.valid, 'new_password': '123', 'confirm_password': '123'},
        ):
            with self.subTest(values=values['new_password']):
                response = self.client.post(self.url, values, content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.check_password(self.valid['current_password']))
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='staff_password_changed').exists())

    def test_not_logged_in_is_denied(self):
        self.client.logout()
        response = self.client.post(self.url, self.valid, content_type='application/json')
        self.assertIn(response.status_code, (401, 403))
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.check_password(self.valid['current_password']))

    def test_participant_not_allowed_to_use_staff_endpoint(self):
        person = self.User.objects.create_user(username='ordinary-participant-password', password='Participant-Strong-OnlyTest-33!')
        self.client.force_login(person)
        response = self.client.post(self.url, {
            'current_password': 'Participant-Strong-OnlyTest-33!',
            'new_password': self.valid['new_password'],
            'confirm_password': self.valid['new_password'],
        }, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_csrf_required(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.operator)
        response = browser.post(self.url, self.valid, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_studio_only_operator_can_change_password(self):
        person = self.User.objects.create_user(
            username='studio-only-password-staff', password='Studio-Strong-OnlyTest-33!',
            is_staff=True, is_active=True,
        )
        person.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_campphotograph',
        ))
        self.client.force_login(person)
        new = 'Evening Sparrow Garden Lantern 2026!'
        response = self.client.post(self.url, {
            'current_password': 'Studio-Strong-OnlyTest-33!',
            'new_password': new, 'confirm_password': new,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        person.refresh_from_db()
        self.assertTrue(person.check_password(new))
