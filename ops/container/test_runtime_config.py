"""Offline startup-policy regression tests; no Django or database imports."""
import unittest
from runtime_config import configure


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
                        {'PAYSTACK_LIVE_ENABLED': 'true'}, {'DAWANA_WEBSITE_ONLY': 'yes'}):
            with self.subTest(names=list(changes)), self.assertRaises(ValueError):
                configure({'PUBLIC_HOST': 'foundation.example.test', **changes})

    def test_explicit_application_mode_preserves_existing_release_path(self):
        env = configure({'PUBLIC_HOST': 'foundation.example.test', 'DAWANA_WEBSITE_ONLY': 'false'})
        self.assertNotIn('PAYSTACK_SECRET_KEY', env)
        self.assertEqual(env['DIC_BACKGROUND_WORKER_ENABLED'], 'true')
        self.assertEqual(env['DIC_PORTAL_ACCOUNTS_ENABLED'], 'true')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertEqual(env['DIC_PORTAL_EMAIL_VERIFY_URL'], 'https://foundation.example.test/dic/participant')


if __name__ == '__main__':
    unittest.main()
