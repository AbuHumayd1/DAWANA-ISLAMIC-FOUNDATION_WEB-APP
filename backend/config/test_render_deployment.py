"""Render startup and health regressions without real credentials or connections."""
import os
import logging
from pathlib import Path
import subprocess
import sys
import textwrap
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, connections
from django.test import SimpleTestCase, override_settings
from django.test.testcases import DatabaseOperationForbidden
from rest_framework.test import APIRequestFactory

from health import views as health_views
from health.views import HealthCheckView, WebHealthCheckView
from .render_logging import RenderRequestPrivacyFilter


class RenderDeploymentTests(SimpleTestCase):
    def settings_process(self, extra=None):
        backend = Path(__file__).resolve().parents[1]
        environment = {key: os.environ[key] for key in
            ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        environment.update(
            DJANGO_SETTINGS_MODULE='config.settings.render',
            PUBLIC_HOST='backend.example.test', FRONTEND_ORIGIN='https://portal.example.test',
            DJANGO_SECRET_KEY='synthetic-render-startup-only-' * 3,
            DATABASE_URL='postgresql://synthetic:unused@database.example.test/render_test')
        environment.update(extra or {})
        code = 'import sys; sys.path.insert(0, ' + repr(str(backend)) + ')\n'
        code += textwrap.dedent('''
            import os
            from unittest.mock import patch
            import environ
            from django.db.backends.base.base import BaseDatabaseWrapper
            def denied(*args, **kwargs):
                raise RuntimeError('External access forbidden during startup regression.')
            with patch.object(environ.Env, 'read_env'), \\
                    patch.object(BaseDatabaseWrapper, 'ensure_connection', denied), \\
                    patch('socket.socket.connect', denied), \\
                    patch('socket.create_connection', denied):
                from django.core.wsgi import get_wsgi_application
                application = get_wsgi_application()
                from django.conf import settings as s
                assert callable(application)
                assert s.DJANGO_DEPLOYMENT_TARGET == 'render'
                assert 'DIC_AUTOMATION_ACTOR_ID' not in os.environ
                assert s.DIC_AUTOMATION_ACTOR_ID == 0
                assert s.DIC_BACKGROUND_WORKER_ENABLED is False
                assert not s.DEFAULT_FROM_EMAIL and not s.RESEND_API_KEY
                assert s.DEBUG is False and s.SECURE_SSL_REDIRECT is True
                assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE
                assert s.DATABASES['default']['OPTIONS']['sslmode'] == 'verify-full'
                assert s.DATABASES['default']['OPTIONS']['sslrootcert']
                assert s.PAYSTACK_LIVE_ENABLED is False
                assert s.CACHES['default']['BACKEND'].endswith('.DatabaseCache')
                assert s.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] == [
                    'rest_framework.permissions.IsAuthenticated']
                assert 'django.middleware.csrf.CsrfViewMiddleware' in s.MIDDLEWARE
                assert 'config.request_security.AdminLoginThrottleMiddleware' in s.MIDDLEWARE
                assert 'config.request_security.TrustedGatewayMiddleware' not in s.MIDDLEWARE
                from django.test import Client
                client = Client(HTTP_HOST='backend.example.test', HTTP_X_FORWARDED_PROTO='https')
                assert client.get('/api/v1/health/web/').status_code == 200
                assert client.get('/api/v1/health/').status_code == 503
                assert client.get('/api/v1/dic/operations/auth/me/').status_code in (401, 403)
                assert client.get('/api/v1/health/web/', HTTP_X_FORWARDED_PROTO='http').status_code == 301
            print('PASS: Render web starts independently with production security.')
        ''')
        # The fixture is only used to inspect settings. No TLS connection is made.
        with TemporaryDirectory() as directory:
            ca = Path(directory) / 'synthetic-unused-ca.pem'
            ca.write_text('Synthetic settings fixture, never used for TLS.', encoding='ascii')
            environment.setdefault('DB_SSLROOTCERT', str(ca))
            return subprocess.run([sys.executable, '-I', '-B', '-c', code],
                env=environment, capture_output=True, text=True, timeout=30)

    def test_render_wsgi_starts_without_worker_actor_delivery_or_database(self):
        result = self.settings_process()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: Render web starts independently', result.stdout)

    def test_render_rejects_weaker_tls_internal_endpoint_and_weak_secret(self):
        for extra in (
            {'DB_SSLMODE': 'require'},
            {'DATABASE_URL': 'postgresql://synthetic:unused@dpg-synthetic/render_test'},
            {'DB_SSLROOTCERT': '/nonexistent-render-ca.pem'},
            {'DJANGO_SECRET_KEY': 'weak'},
        ):
            with self.subTest(extra=extra):
                result = self.settings_process(extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ImproperlyConfigured', result.stderr)

    @override_settings(DIC_BACKGROUND_WORKER_ENABLED=True, DIC_WORKER_HEARTBEAT_CACHE=True)
    def test_web_probe_never_accesses_database_cache_or_delivery(self):
        with patch('health.views.connection') as database, \
                patch('config.worker_health.healthy') as heartbeat, \
                patch('dic.recovery.channel_available') as delivery:
            response = WebHealthCheckView.as_view()(APIRequestFactory().get('/api/v1/health/web/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        database.cursor.assert_not_called()
        heartbeat.assert_not_called()
        delivery.assert_not_called()

    @override_settings(HEALTH_CHECK_WORKERS=False, DIC_BACKGROUND_WORKER_ENABLED=True)
    def test_render_database_probe_does_not_require_worker_or_delivery(self):
        with patch('health.views.connection') as database, \
                patch('config.worker_health.healthy') as heartbeat, \
                patch('dic.recovery.channel_available') as delivery:
            response = HealthCheckView.as_view()(APIRequestFactory().get('/api/v1/health/'))
        self.assertEqual(response.status_code, 200)
        database.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SELECT 1')
        heartbeat.assert_not_called()
        delivery.assert_not_called()

    def test_database_and_unexpected_failures_are_safe_logged_503s(self):
        for error in (OperationalError, OSError, ImproperlyConfigured, RuntimeError):
            with self.subTest(error=error), \
                    patch('health.views.connection') as database, \
                    self.assertLogs('health.views', level='WARNING') as logs:
                database.cursor.side_effect = error('secret-connection-detail')
                response = HealthCheckView.as_view()(APIRequestFactory().get('/api/v1/health/'))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data, {'status': 'unavailable'})
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertNotIn('secret-connection-detail', '\n'.join(logs.output))

    def test_connection_mock_and_settings_restore_after_exception(self):
        original_binding = health_views.connection
        real_connection = connections['default']
        original_cursor = real_connection.cursor
        missing = object()
        original_setting = getattr(settings, 'HEALTH_CHECK_WORKERS', missing)
        # Exercise the actual probe tests, so reintroducing a proxy-attribute
        # patch is caught here rather than only during later class cleanup.
        for name in (
            'test_web_probe_never_accesses_database_cache_or_delivery',
            'test_render_database_probe_does_not_require_worker_or_delivery',
            'test_database_and_unexpected_failures_are_safe_logged_503s',
        ):
            with self.subTest(probe=name):
                getattr(self, name)()
                self.assertIs(health_views.connection, original_binding)
                self.assertIs(real_connection.cursor, original_cursor)
                self.assertIs(getattr(settings, 'HEALTH_CHECK_WORKERS', missing), original_setting)
        # Patch the module binding, never an attribute of Django's proxy: proxy
        # attribute cleanup can delete SimpleTestCase's real query guard.
        with self.assertRaisesMessage(RuntimeError, 'simulated test failure'):
            with self.settings(HEALTH_CHECK_WORKERS=False), \
                    patch('health.views.connection') as database:
                database.cursor.side_effect = OperationalError('synthetic failure')
                self.assertIs(real_connection.cursor, original_cursor)
                raise RuntimeError('simulated test failure')
        self.assertIs(health_views.connection, original_binding)
        self.assertIs(real_connection.cursor, original_cursor)
        self.assertIs(getattr(settings, 'HEALTH_CHECK_WORKERS', missing), original_setting)
        with self.assertRaises(DatabaseOperationForbidden):
            real_connection.cursor()

    def test_render_server_error_logs_retain_locations_without_private_details(self):
        try:
            raise RuntimeError('postgresql://private:password@host/database?token=secret')
        except RuntimeError:
            record = logging.LogRecord('django.request', logging.ERROR, __file__, 0,
                'Failed /private?token=secret', (), sys.exc_info())
        record.status_code = 500
        RenderRequestPrivacyFilter().filter(record)
        self.assertIn('RuntimeError', record.getMessage())
        self.assertIn('test_render_deployment.py:', record.getMessage())
        for value in ('password', 'postgresql://', 'token=secret', '/private'):
            self.assertNotIn(value, record.getMessage())
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.exc_text)
