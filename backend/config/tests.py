import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .staging_email import SandboxEmailBackend
from .staging_logging import RequestPrivacyFilter


class StagingDeploymentTests(SimpleTestCase):
    def settings_process(self, extra=None):
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings.staging',
               'DJANGO_SECRET_KEY': 'isolated-staging-settings-validation-key-' * 3,
               'DATABASE_URL': 'postgresql://example:unused@staging-db.invalid/staging_test',
               'DB_TEST_NAME': 'test_staging_test', 'STAGING_DATABASE_NAME': 'staging_test', 'DJANGO_DEBUG': 'True',
               'DJANGO_ALLOWED_HOSTS': 'backend-staging.onrender.com',
               'DJANGO_CORS_ALLOWED_ORIGINS': 'https://frontend-staging.netlify.app',
               'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://frontend-staging.netlify.app',
               'PAYSTACK_MODE': 'test', 'PAYSTACK_SECRET_KEY': '', 'STAGING_EMAIL_ENABLED': 'False',
               **(extra or {})}
        code = ('import sys;sys.path[:0]=' + repr(sys.path) + ';import django;django.setup();'
                'from django.conf import settings as s;import json;'
                'print(json.dumps(dict(debug=s.DEBUG,secure=s.SESSION_COOKIE_SECURE,'
                'same_site=s.SESSION_COOKIE_SAMESITE,db=s.DATABASES["default"]["NAME"],'
                'ssl=s.DATABASES["default"]["OPTIONS"]["sslmode"],'
                'worker=s.DIC_RECOVERY_DELIVERY_WORKER_ENABLED,sms=s.DIC_SMS_RECOVERY_ADAPTER,'
                'whatsapp=s.DIC_WHATSAPP_ACCESS_TOKEN,email=s.EMAIL_HOST,'
                'cache=s.CACHES["default"]["BACKEND"],middleware=s.MIDDLEWARE)))')
        return subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                              env=env, text=True, capture_output=True, timeout=30)

    def test_staging_reuses_production_security_and_disables_real_channels(self):
        result = self.settings_process({'DIC_RECOVERY_DELIVERY_WORKER_ENABLED': 'True',
                                        'DIC_SMS_RECOVERY_ADAPTER': 'unsafe.adapter',
                                        'DIC_WHATSAPP_ACCESS_TOKEN': 'not-real', 'EMAIL_HOST': 'unsafe.invalid'})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['debug']); self.assertTrue(data['secure'])
        self.assertEqual(data['same_site'], 'Lax'); self.assertEqual(data['ssl'], 'require')
        self.assertEqual(data['db'], 'staging_test'); self.assertFalse(data['worker'])
        self.assertEqual((data['sms'], data['whatsapp'], data['email']), ('', '', ''))
        self.assertIn('DatabaseCache', data['cache'])
        self.assertEqual(data['middleware'][1], 'whitenoise.middleware.WhiteNoiseMiddleware')

    def test_staging_rejects_live_keys_wildcards_insecure_origins_and_sqlite(self):
        for env in [ {'PAYSTACK_MODE': 'live'}, {'PAYSTACK_SECRET_KEY': 'sk_live_not_real'},
                     {'DJANGO_ALLOWED_HOSTS': '*'}, {'DJANGO_CORS_ALLOWED_ORIGINS': 'http://unsafe.invalid'},
                     {'DATABASE_URL': 'sqlite:///not-used.sqlite3'}, {'STAGING_DATABASE_NAME': 'wrong_database'} ]:
            with self.subTest(env=env):
                self.assertNotEqual(self.settings_process(env).returncode, 0)

    def test_sandbox_configuration_rejects_real_participant_addresses(self):
        result = self.settings_process({'STAGING_EMAIL_ENABLED': 'True',
            'STAGING_EMAIL_HOST': 'smtp-sandbox.invalid', 'STAGING_EMAIL_RECIPIENTS': 'real@example.com',
            'DIC_RECOVERY_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('non-routable .test', result.stderr)

    @override_settings(DIC_EMAIL_RECOVERY_ENABLED=True, STAGING_EMAIL_RECIPIENTS=['guardian@example.test'])
    def test_sandbox_mail_allowlist_is_enforced_before_smtp(self):
        backend = SandboxEmailBackend()
        with patch('django.core.mail.backends.smtp.EmailBackend.send_messages', return_value=1) as send:
            self.assertEqual(backend.send_messages([EmailMessage('test', 'test', to=['guardian@example.test'])]), 1)
            with self.assertRaises(ImproperlyConfigured):
                backend.send_messages([EmailMessage('test', 'test', to=['real@example.com'])])
            with self.assertRaises(ImproperlyConfigured):
                backend.send_messages([EmailMessage('test', 'test', to=['guardian@example.test'], bcc=['real@example.com'])])
            send.assert_called_once()

    def test_request_logs_omit_paths_query_payload_and_exception_details(self):
        record = logging.LogRecord('django.request', logging.ERROR, '', 0,
            'Failed /participant/private?code=123456', (), (ValueError, ValueError('private contact'), None))
        record.status_code = 500
        RequestPrivacyFilter().filter(record)
        self.assertEqual(record.getMessage(), 'HTTP request rejected or failed (status=500).')
        self.assertIsNone(record.exc_info)
