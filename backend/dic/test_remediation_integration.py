"""Disposable PostgreSQL only, discovered by the existing core CI partition."""
from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.conf import settings
from config.request_security import AdminLoginThrottleMiddleware
from .test_allocation import AllocationFixtures
from .allocation import paid_participants
from .models import RegistrationOrder


class SettlementHousingTests(AllocationFixtures, TestCase):
    def test_invalid_evidence_and_foreign_edition_never_qualify_for_housing(self):
        edition = self.make_edition()
        participant = self.make_participant(edition)
        order = RegistrationOrder.objects.get(items__participant=participant)
        self.assertTrue(paid_participants(edition).filter(pk=participant.pk).exists())
        other_mode = 'live' if settings.PAYSTACK_MODE == 'test' else 'test'
        for changes in ({'provider_mode': other_mode}, {'provider_status': 'pending'},
                        {'provider_reported_amount_kobo': 1}, {'provider_reported_currency': 'USD'},
                        {'verified_at': None}, {'status': 'reconcile'}):
            with self.subTest(changes=changes):
                attempt = order.payment_attempts.get()
                original = {key: getattr(attempt, key) for key in changes}
                order.payment_attempts.update(**changes)
                self.assertFalse(paid_participants(edition).filter(pk=participant.pk).exists())
                order.payment_attempts.update(**original)
        other = self.make_edition(year=2097)
        self.assertFalse(paid_participants(other).filter(pk=participant.pk).exists())


class AdminDurableThrottleTests(TestCase):
    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
    def test_standard_admin_still_requires_staff_credentials_and_csrf(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.conf import settings
        user = get_user_model().objects.create_user(username='synthetic-admin', password='synthetic-password', is_staff=True)
        with self.settings(MIDDLEWARE=[*settings.MIDDLEWARE, 'config.request_security.AdminLoginThrottleMiddleware']):
            client = Client(enforce_csrf_checks=True)
            self.assertEqual(client.get('/admin/').status_code, 302)
            self.assertEqual(client.post('/admin/login/', {'username': user.username, 'password': 'synthetic-password'}).status_code, 403)
            client.get('/admin/login/')
            token = client.cookies['csrftoken'].value
            response = client.post('/admin/login/', {'username': user.username, 'password': 'synthetic-password', 'csrfmiddlewaretoken': token})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get('/admin/').status_code, 200)

    def test_durable_limit_isolated_by_verified_ip_and_not_forwarded_header(self):
        middleware = AdminLoginThrottleMiddleware(lambda request: HttpResponse())
        factory = RequestFactory()
        for _ in range(10):
            self.assertIsNone(middleware.process_request(factory.post('/admin/login/', {'username': 'staff'}, REMOTE_ADDR='192.0.2.1')))
        self.assertEqual(middleware.process_request(factory.post('/admin/login/', {'username': 'staff'},
            REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='198.51.100.3')).status_code, 429)
        self.assertIsNone(middleware.process_request(factory.post('/admin/login/', {'username': 'staff'}, REMOTE_ADDR='192.0.2.2')))
