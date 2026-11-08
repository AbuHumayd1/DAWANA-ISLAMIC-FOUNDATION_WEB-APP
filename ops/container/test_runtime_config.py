"""Offline startup-policy regression tests; no Django or database imports."""
import unittest
from runtime_config import configure, validate_inputs
from startup_errors import StartupError
from unittest.mock import patch


class RuntimeConfigTests(unittest.TestCase):
    def test_minimal_inputs_derive_internal_security_and_disable_payments(self):
        env = configure({'PUBLIC_HOST': 'foundation.example.test'})
        self.assertEqual(env['DJANGO_ALLOWED_HOSTS'], 'foundation.example.test')
        self.assertEqual(env['DJANGO_CSRF_TRUSTED_ORIGINS'], 'https://foundation.example.test')
        self.assertEqual(env['DB_SSLMODE'], 'verify-full')
        self.assertEqual(env['PAYSTACK_SECRET_KEY'], '')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertEqual(env['DAWANA_WEBSITE_ONLY'], 'true')

    def test_conflicting_security_and_collection_fail_closed(self):
        for changes in ({'DB_SSLMODE': 'require'}, {'DJANGO_ALLOWED_HOSTS': '*'},
                        {'DAWANA_TRUSTED_GATEWAYS': '0.0.0.0/0'},
                        {'PAYSTACK_MODE': 'live'}, {'PAYSTACK_SECRET_KEY': 'synthetic'},
                        {'PAYSTACK_LIVE_ENABLED': 'true'}, {'DAWANA_WEBSITE_ONLY': 'invalid'}):
            with self.subTest(names=list(changes)), self.assertRaises(ValueError):
                configure({'PUBLIC_HOST': 'foundation.example.test', **changes})

    def test_equivalent_legacy_values_preserve_the_same_security_policy(self):
        env = configure(dict(PUBLIC_HOST='foundation.example.test', DJANGO_TRUST_PROXY_HTTPS='True',
            DJANGO_DEBUG='0', DAWANA_WEBSITE_ONLY='TRUE', PAYSTACK_LIVE_ENABLED='False',
            DJANGO_ALLOWED_HOSTS='foundation.example.test, foundation.example.test',
            DJANGO_CSRF_TRUSTED_ORIGINS=' https://foundation.example.test ',
            DJANGO_CORS_ALLOWED_ORIGINS='https://foundation.example.test'))
        self.assertEqual(env['DJANGO_TRUST_PROXY_HTTPS'], 'true')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertEqual(env['DJANGO_ALLOWED_HOSTS'], 'foundation.example.test')
        self.assertEqual(env['DJANGO_CORS_ALLOWED_ORIGINS'], 'https://foundation.example.test')

    def test_legacy_database_fields_are_supported_without_creating_a_url(self):
        env = configure(dict(PUBLIC_HOST='foundation.example.test', DJANGO_SECRET_KEY='x'*64,
            DB_HOST='synthetic-db.example.test', DB_NAME='synthetic', DB_USER='synthetic', DB_PASSWORD='private'))
        validate_inputs(env)
        self.assertNotIn('DATABASE_URL', env)
        self.assertEqual(env['DB_PASSWORD'], 'private')
        self.assertEqual(env['DB_SSLMODE'], 'verify-full')

    def test_database_tls_and_secret_diagnostics_do_not_disclose_supplied_values(self):
        baseline = dict(PUBLIC_HOST='foundation.example.test', DJANGO_SECRET_KEY='x'*64,
            DATABASE_URL='postgresql://synthetic:private@synthetic-db.example.test/synthetic')
        cases = [({'DJANGO_SECRET_KEY': 'private'}, 'CFG_SECRET_KEY'),
                 ({'DATABASE_URL': 'postgresql://synthetic:private@synthetic-db.example.test/synthetic?sslmode=require'}, 'CFG_DATABASE_URL_TLS'),
                 ({'DATABASE_URL': 'not-a-url-private'}, 'CFG_DATABASE_URL'),
                 ({'DB_SSLROOTCERT': '/private/not-mounted.pem'}, 'CFG_DATABASE_CA_FILE')]
        for changes, code in cases:
            with self.subTest(code=code), self.assertRaises(StartupError) as error:
                validate_inputs(configure({**baseline, **changes}))
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('private', str(error.exception))
            self.assertNotIn('synthetic-db', str(error.exception))

    def test_conflicting_origin_is_rejected_without_echoing_it(self):
        with self.assertRaises(StartupError) as error:
            configure({'PUBLIC_HOST': 'foundation.example.test', 'DJANGO_CORS_ALLOWED_ORIGINS': 'https://private.example.test'})
        self.assertEqual(error.exception.code, 'CFG_CONFLICT_DJANGO_CORS_ALLOWED_ORIGINS')
        self.assertNotIn('private.example.test', str(error.exception))

    def test_custom_ca_must_be_a_readable_mounted_file(self):
        env = configure(dict(PUBLIC_HOST='foundation.example.test', DJANGO_SECRET_KEY='x'*64,
            DB_HOST='synthetic-db.example.test', DB_NAME='synthetic', DB_USER='synthetic',
            DB_SSLROOTCERT='/run/secrets/synthetic-ca.pem'))
        with patch('runtime_config.os.path.isfile', return_value=True), patch('runtime_config.os.access', return_value=False):
            with self.assertRaises(StartupError) as error:
                validate_inputs(env)
        self.assertEqual(error.exception.code, 'CFG_DATABASE_CA_FILE')
        with patch('runtime_config.os.path.isfile', return_value=True), patch('runtime_config.os.access', return_value=True):
            validate_inputs(env)

    def test_explicit_application_mode_preserves_existing_release_path(self):
        env = configure({'PUBLIC_HOST': 'foundation.example.test', 'DAWANA_WEBSITE_ONLY': 'false'})
        self.assertNotIn('PAYSTACK_SECRET_KEY', env)
        self.assertEqual(env['DIC_BACKGROUND_WORKER_ENABLED'], 'true')
        self.assertEqual(env['DIC_PORTAL_ACCOUNTS_ENABLED'], 'true')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertEqual(env['DIC_PORTAL_EMAIL_VERIFY_URL'], 'https://foundation.example.test/dic/participant')


if __name__ == '__main__':
    unittest.main()
