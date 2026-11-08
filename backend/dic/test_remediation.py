"""Database-free regression contracts for the production remediation sprint."""
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from config.deployment_security import application_bind, validate_database_tls
from config.release_migrations import validate_target
from .settlement_evidence import settlement_reason, order_has_verified_settlement


@override_settings(PAYSTACK_MODE='live', SETTINGS_MODULE='config.settings.production')
class RemediationPolicyTests(SimpleTestCase):
    def attempt(self):
        now = timezone.now()
        revision = NS(pk=2, order_id=1, accepted_at=now, early_bird_cutoff_at=None,
                      items=Mock())
        revision.items.all.return_value = [NS(price_type='regular', early_bird_fee_snapshot_ngn=None)]
        order = NS(pk=1, registration_basis='paid', status='confirmed', payment_status='paid',
                   current_price_revision=revision, total_amount_ngn=Decimal('100'))
        return NS(order=order, status='successful', provider_mode='live', price_revision_id=2,
                  amount_kobo=10000, currency='NGN', provider_status='success',
                  provider_reported_amount_kobo=10000, provider_reported_currency='NGN',
                  provider_transaction_id='synthetic', verified_at=now, provider_paid_at=now)

    def test_valid_live_financial_evidence_and_invalid_variants(self):
        self.assertEqual(settlement_reason(self.attempt()), '')
        for field, value in [('provider_mode', 'test'), ('currency', 'USD'), ('amount_kobo', 1),
                ('provider_reported_amount_kobo', 1), ('provider_status', 'pending'),
                ('provider_reported_currency', 'USD'), ('provider_transaction_id', ''),
                ('verified_at', None), ('provider_paid_at', None), ('price_revision_id', 3)]:
            attempt = self.attempt()
            setattr(attempt, field, value)
            with self.subTest(field=field):
                self.assertTrue(settlement_reason(attempt))

    def test_test_receipt_is_never_production_revenue_even_in_test_configuration(self):
        attempt = self.attempt()
        attempt.provider_mode = 'test'
        with self.settings(PAYSTACK_MODE='test', SETTINGS_MODULE='config.settings.production'):
            self.assertEqual(settlement_reason(attempt), 'provider_mode_review')

    def test_reconciliation_blocks_new_housing_and_tutors_are_not_financial_income(self):
        attempt = self.attempt()
        attempt.order.payment_attempts = Mock()
        attempt.order.payment_attempts.select_related.return_value = [attempt, NS(status='reconcile')]
        self.assertFalse(order_has_verified_settlement(attempt.order))
        attempt.order.registration_basis = 'tutor'
        self.assertEqual(settlement_reason(attempt), 'complimentary_registration_not_revenue')

    def test_refund_reporting_does_not_implicitly_mutate_entitlement(self):
        attempt = self.attempt()
        attempt.order.payment_status = 'refunded'
        self.assertEqual(settlement_reason(attempt), 'refunded')
        self.assertEqual(settlement_reason(attempt, allow_refunded=True), '')
        self.assertEqual(attempt.order.payment_status, 'refunded')

    def test_managed_binding_requires_explicit_address_and_never_downgrades_tls(self):
        self.assertEqual(application_bind({}), '127.0.0.1:10000')
        self.assertEqual(application_bind({'DJANGO_DEPLOYMENT_TARGET': 'managed',
            'DJANGO_BIND_ADDRESS': '0.0.0.0', 'PORT': '12345'}), '0.0.0.0:12345')
        for env in ({'DJANGO_DEPLOYMENT_TARGET': 'managed'},
                    {'DJANGO_BIND_ADDRESS': '0.0.0.0'}, {'PORT': 'bad', 'DJANGO_DEPLOYMENT_TARGET': 'render'}):
            with self.assertRaises(ValueError): application_bind(env)
        validate_database_tls('managed', 'database.example.test', 'verify-full')
        with self.assertRaises(ImproperlyConfigured): validate_database_tls('managed', 'database.example.test', 'require')

    def test_migration_identity_rejects_same_name_wrong_host_cluster_or_role(self):
        expected = dict(database='fresh_release', host='database.example.test', port='5432', role='migration_owner', cluster_id='123')
        config = dict(HOST=expected['host'], PORT='5432', USER=expected['role'])
        actual = dict(database='fresh_release', role='migration_owner', cluster_id='123')
        validate_target(config, expected, actual)
        for key, value in [('database', 'other'), ('cluster_id', '456'), ('role', 'other')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate_target(config, expected, {**actual, key: value})
        with self.assertRaises(RuntimeError): validate_target({**config, 'HOST': 'other.example.test'}, expected, actual)

    def test_restricted_administrator_permission_remains_absent(self):
        from .management.commands.setup_dic_staff_roles import Command
        self.assertNotIn('can_manage_registration_access', Command.GROUP_PERMISSIONS['DIC Administrators'])

    def test_existing_operations_permission_is_global_not_an_edition_assignment(self):
        from .operations_api import OperationsSessionPermission
        actor = NS(is_authenticated=True, is_superuser=False,
                   has_perm=lambda name: name == 'dic.can_view_dic_operations')
        for edition in ('1', '2'):
            request = NS(user=actor, query_params={'edition': edition})
            self.assertTrue(OperationsSessionPermission().has_permission(request, None))
        actor.has_perm = lambda name: False
        self.assertFalse(OperationsSessionPermission().has_permission(request, None))

    def test_runtime_gate_fails_without_fonts_and_never_skips_missing_probe(self):
        from config.runtime_requirements import verify_runtime
        with patch('config.runtime_requirements.sys.version_info', (3, 13)), \
                patch('config.runtime_requirements.version', return_value='5.2.18'), \
                patch('config.runtime_requirements.Path.is_file', return_value=False):
            with self.assertRaisesMessage(RuntimeError, 'Liberation'):
                verify_runtime()
        for unsupported in ((3, 11), (3, 14), (4, 0)):
            with self.subTest(runtime=unsupported), patch('config.runtime_requirements.sys.version_info', unsupported):
                with self.assertRaisesMessage(RuntimeError, 'Python 3.12 or 3.13'):
                    verify_runtime()
        with patch('config.runtime_requirements.sys.version_info', (3, 13)), \
                patch('config.runtime_requirements.version', return_value='5.2.18'), \
                patch('config.runtime_requirements.os.environ', {}), \
                patch('config.runtime_requirements.shutil.which', return_value=None), \
                patch('config.runtime_requirements.Path.is_file', autospec=True,
                      side_effect=lambda path: path.name != 'ffprobe'):
            with self.assertRaisesMessage(RuntimeError, 'ffprobe'):
                verify_runtime()

    def test_runtime_gate_accepts_native_312_and_retained_313_without_skipping_checks(self):
        from config.runtime_requirements import verify_runtime
        for runtime in ((3, 12), (3, 13)):
            with self.subTest(runtime=runtime), \
                    patch('config.runtime_requirements.sys.version_info', runtime), \
                    patch('config.runtime_requirements.version', return_value='5.2.18') as packages, \
                    patch('config.runtime_requirements.Path.is_file', return_value=True), \
                    patch('config.runtime_requirements.os.environ', {}), \
                    patch('config.runtime_requirements.shutil.which', return_value='/usr/bin/ffprobe'), \
                    patch('config.runtime_requirements.subprocess.run') as probe:
                verify_runtime()
                self.assertEqual([call.args[0] for call in packages.call_args_list],
                    ['Django', 'gunicorn', 'reportlab', 'Pillow', 'qrcode', 'psycopg'])
                self.assertEqual(probe.call_args.args[0], ['/usr/bin/ffprobe', '-version'])
                self.assertTrue(probe.call_args.kwargs['check'])
