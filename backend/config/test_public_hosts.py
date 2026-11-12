"""Exact dual-host routing through production ingress; no database/network."""
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from .native_defaults import configure
from .release_security import validate_production


RENDER_HOST = 'dawana-islamic-foundation-web-app-1.onrender.com'
API_HOST = 'api.dawanaislamicfoundation.org'
FRONTEND = 'https://dawanaislamicfoundation.org'


class PublicHostTests(SimpleTestCase):
    def environment(self, **extra):
        return configure({'PUBLIC_HOST': RENDER_HOST, 'FRONTEND_ORIGIN': FRONTEND, **extra})

    def test_existing_configuration_remains_single_host_and_ignores_stale_override(self):
        result = self.environment(DJANGO_ALLOWED_HOSTS='*')
        self.assertEqual(result['DJANGO_ALLOWED_HOSTS'], RENDER_HOST)

    def test_alias_adds_only_explicit_host_without_changing_origins_or_payments(self):
        result = self.environment(PUBLIC_HOST_ALIASES=API_HOST,
            PAYSTACK_MODE='live', PAYSTACK_LIVE_ENABLED='true', PAYSTACK_SECRET_KEY='synthetic-preserved',
            PAYSTACK_CALLBACK_URL=FRONTEND + '/dic/register/payment-return')
        self.assertEqual(result['DJANGO_ALLOWED_HOSTS'].split(','), [RENDER_HOST, API_HOST])
        self.assertEqual(result['DJANGO_CSRF_TRUSTED_ORIGINS'], FRONTEND)
        self.assertEqual(result['DJANGO_CORS_ALLOWED_ORIGINS'], FRONTEND)
        self.assertEqual(result['PAYSTACK_MODE'], 'live')
        self.assertEqual(result['PAYSTACK_LIVE_ENABLED'], 'true')
        self.assertEqual(result['PAYSTACK_SECRET_KEY'], 'synthetic-preserved')
        self.assertEqual(result['PAYSTACK_CALLBACK_URL'], FRONTEND + '/dic/register/payment-return')
        self.assertEqual(self.environment(PUBLIC_HOST_ALIASES=f'{API_HOST},{RENDER_HOST},{API_HOST}')
                         ['DJANGO_ALLOWED_HOSTS'], f'{RENDER_HOST},{API_HOST}')

    def test_invalid_aliases_fail_closed(self):
        for alias in ('*', '.dawanaislamicfoundation.org', '*.onrender.com',
                      'https://' + API_HOST, API_HOST + ':443', API_HOST + '/',
                      API_HOST + '?query=1', 'user@' + API_HOST, API_HOST + ',',
                      ',' + API_HOST, API_HOST + ',,' + RENDER_HOST,
                      ' ' + API_HOST, API_HOST + '\n', 'localhost'):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                self.environment(PUBLIC_HOST_ALIASES=alias)
        with self.assertRaises(ValueError):
            self.environment(PUBLIC_HOST=f'{RENDER_HOST},{API_HOST}')

    def test_both_health_hosts_work_and_foreign_or_forwarded_hosts_cannot_bypass_validation(self):
        hosts = self.environment(PUBLIC_HOST_ALIASES=API_HOST)['DJANGO_ALLOWED_HOSTS'].split(',')
        with self.settings(ROOT_URLCONF='config.urls', DEBUG=False, ALLOWED_HOSTS=hosts,
                SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
                USE_X_FORWARDED_HOST=False, SECURE_SSL_REDIRECT=True, HEALTH_CHECK_WORKERS=False,
                MIDDLEWARE=['config.native_security.ManagedHttpsMiddleware',
                            'django.middleware.security.SecurityMiddleware']), \
                patch('health.views.connection') as database:
            client = Client(HTTP_X_FORWARDED_PROTO='https')
            for host in hosts:
                response = client.get('/api/v1/health/', HTTP_HOST=host)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'status': 'ok'})
                self.assertEqual(client.get('/api/v1/health/', HTTP_HOST=host,
                    HTTP_X_FORWARDED_PROTO='http').status_code, 301)
            for host in ('attacker.example', 'other.onrender.com', API_HOST + '.attacker.example',
                         'nested.' + API_HOST):
                self.assertEqual(client.get('/api/v1/health/', HTTP_HOST=host,
                    HTTP_X_FORWARDED_HOST=API_HOST).status_code, 400)
            database.cursor.assert_called()

    def test_production_validator_accepts_two_exact_hosts_and_still_rejects_wildcards(self):
        from dic.test_release_readiness import ReleaseReadinessTests
        config = ReleaseReadinessTests().config()
        config['ALLOWED_HOSTS'] = self.environment(PUBLIC_HOST_ALIASES=API_HOST)['DJANGO_ALLOWED_HOSTS'].split(',')
        validate_production(config)
        for hosts in (['*'], [RENDER_HOST, '.dawanaislamicfoundation.org'], [RENDER_HOST, '*.onrender.com']):
            from django.core.exceptions import ImproperlyConfigured
            with self.subTest(hosts=hosts), self.assertRaises(ImproperlyConfigured):
                validate_production({**config, 'ALLOWED_HOSTS': hosts})
