"""Database-free release contracts; never apply migration plans or grants."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from io import StringIO
from types import SimpleNamespace as NS
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory,force_authenticate
from config.release_security import validate_production
from config.release_migrations import validate_approval,digest,plan_manifest,validate_target
from .management.commands.setup_dic_staff_roles import Command
from .operations_api import OperationsParticipantListView,OperationsRegistrationListView,OperationsDashboardView,OperationsReportView
from dic_finance.services import financial_totals


class ReleaseReadinessTests(SimpleTestCase):
    def config(self):
        return dict(DEBUG=False,SECRET_KEY='synthetic-'+('x'*60),ALLOWED_HOSTS=['backend.example.test'],
            CORS_ALLOWED_ORIGINS=['https://portal.example.test'],CSRF_TRUSTED_ORIGINS=['https://portal.example.test'],
            SECURE_SSL_REDIRECT=True,SESSION_COOKIE_SECURE=True,CSRF_COOKIE_SECURE=True,
            PAYSTACK_MODE='test',PAYSTACK_SECRET_KEY='sk_test_synthetic',
            DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','HOST':'database.example.test','OPTIONS':{'sslmode':'verify-full'}}},
            PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'],
            CACHES={'default':{'BACKEND':'django.core.cache.backends.db.DatabaseCache'}})

    def test_strict_production_configuration(self):
        validate_production(self.config())
        for key,value in [('DEBUG',True),('SECRET_KEY','short'),('ALLOWED_HOSTS',['*']),
                ('CSRF_TRUSTED_ORIGINS',[]),('CORS_ALLOWED_ORIGINS',['http://portal.example.test']),
                ('CORS_ALLOW_ALL_ORIGINS',True),('CORS_ALLOWED_ORIGIN_REGEXES',['.*']),
                ('PAYSTACK_MODE','live'),('PAYSTACK_SECRET_KEY','sk_live_synthetic'),
                ('SESSION_COOKIE_SECURE',False),('PASSWORD_HASHERS',['django.contrib.auth.hashers.MD5PasswordHasher']),
                ('CACHES',{'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}})]:
            with self.subTest(key=key),self.assertRaises(ImproperlyConfigured):validate_production({**self.config(),key:value})

    def test_exact_migration_approval_requires_backup_and_rollback(self):
        manifest={'database':'release_synthetic','steps':[{'app':'dic','name':'0027_feedback_welfare'}]}
        approval=dict(manifest=deepcopy(manifest),approved_by='Synthetic approver',approved_at='2026-10-28',
            backup_reference='synthetic backup',restore_procedure='synthetic restore',rollback_decision='restore before traffic')
        validate_approval(manifest,approval)
        for key in ('approved_by','backup_reference','restore_procedure','rollback_decision'):
            with self.subTest(key=key),self.assertRaises(RuntimeError):validate_approval(manifest,{**approval,key:''})
        changed=deepcopy(manifest);changed['steps'].append({'app':'dic','name':'0031_phase5_feedback_welfare'})
        with self.assertRaises(RuntimeError):validate_approval(changed,approval)
        self.assertNotEqual(digest(manifest),digest(changed))
        for invalid in (None,[], 'approval'):
            with self.assertRaises(RuntimeError):validate_approval(manifest,invalid)

    def test_staff_role_default_is_preview_only_without_database_calls(self):
        with patch('dic.management.commands.setup_dic_staff_roles.Group.objects') as groups:
            command=Command(stdout=StringIO());command.handle(apply_reviewed_grants=False)
            self.assertEqual(groups.mock_calls,[])
        grants=Command.GROUP_PERMISSIONS['DIC Administrators']
        self.assertNotIn('can_view_dic_finance',grants);self.assertNotIn('view_participant',grants)
        self.assertNotIn('can_view_dic_welfare',grants)

    def test_migration_manifest_rejects_backward_steps_and_records_ordering(self):
        class SyntheticMigration:
            app_label='dic'
            name='synthetic_only'
            dependencies=[('dic','0026_house_score_transaction')]
            run_before=[('dic','0027_feedback_welfare')]
        # This module's real source file supplies a stable fixture hash; no ORM.
        migration=SyntheticMigration()
        manifest=plan_manifest(None,[(migration,False)],'synthetic-release','source-only')
        self.assertEqual(manifest['steps'][0]['run_before'],[['dic','0027_feedback_welfare']])
        self.assertEqual(len(manifest['steps'][0]['source_sha256']),64)
        with self.assertRaises(RuntimeError):plan_manifest(None,[(migration,True)],'synthetic-release','source-only')

    def test_general_operations_cannot_read_identifiable_records(self):
        actor=NS(is_authenticated=True,is_active=True,is_staff=True,is_superuser=False,
            has_perm=lambda key:key=='dic.can_view_dic_operations')
        for view in (OperationsParticipantListView,OperationsRegistrationListView,OperationsDashboardView):
            request=APIRequestFactory().get('/?edition=1');force_authenticate(request,user=actor)
            self.assertEqual(view.as_view()(request).status_code,403)

    def test_export_permission_alone_does_not_export_personal_records(self):
        actor=NS(is_authenticated=True,is_active=True,is_staff=True,is_superuser=False,
            has_perm=lambda key:key in ('dic.can_view_dic_operations','dic.can_export_dic_reports'))
        for report in ('participants','registrations','houses'):
            request=APIRequestFactory().get('/?report='+report+'&edition=1');force_authenticate(request,user=actor)
            with patch('dic.operations_api._edition_from_request',return_value=NS(pk=1)):
                self.assertEqual(OperationsReportView.as_view()(request).status_code,403)

    def test_financial_cash_commitments_and_budget_remain_distinct(self):
        payments=[dict(verified_kobo=7500,gross_verified_kobo=10000,adjustment_kobo=2500,status='successful',exception='')]
        records=[dict(kind='expense',status='approved',amount_kobo=900),dict(kind='expense',status='paid',amount_kobo=500)]
        result=financial_totals(payments,records,[dict(amount_kobo=5000)],500)
        self.assertEqual(result['gross_verified_collections_kobo'],10000)
        self.assertEqual(result['recorded_adjustments_kobo'],2500)
        self.assertEqual(result['net_verified_collections_kobo'],7500)
        self.assertEqual(result['expenditure_kobo'],500);self.assertEqual(result['approved_unpaid_kobo'],900)
        self.assertEqual(result['net_position_kobo'],7000);self.assertIsNone(result['available_operating_balance_kobo'])

    def migration_options(self):
        return dict(database_name='release_synthetic', hostname='database.example.test',
            port='5432', role='release_owner', cluster_id='123456789',
            approval_file=None, apply_approved_plan=False, manifest_file=None)

    @contextmanager
    def migration_environment(self, module='config.settings.render'):
        from .management.commands import release_migrations as release
        database = dict(ENGINE='django.db.backends.postgresql', NAME='release_synthetic',
            HOST='database.example.test', PORT='5432', USER='release_owner')
        with self.settings(SETTINGS_MODULE=module, DATABASES={'default': database}), \
                patch.object(release, 'connection') as connection, \
                patch.object(release, 'MigrationExecutor') as factory, \
                patch.object(release, 'plan_manifest', return_value={'steps': ['pending']}) as manifest:
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (
                'release_synthetic', 'release_owner', '123456789')
            executor = factory.return_value
            executor.loader.detect_conflicts.return_value = {}
            executor.loader.graph.leaf_nodes.return_value = [('dic', '0039_camper_fulfillment')]
            executor.migration_plan.return_value = [('synthetic pending plan', False)]
            yield release.Command(stdout=StringIO()), connection, executor, manifest

    def test_render_release_planning_recognizes_settings_but_never_applies_pending_plan(self):
        from django.core.management.base import CommandError
        for module in ('config.settings.render', 'config.settings.production', 'config.settings.staging'):
            with self.subTest(module=module), self.migration_environment(module) as (command, connection, executor, manifest):
                with self.assertRaisesMessage(CommandError, 'Pending migrations require approval'):
                    command.handle(**self.migration_options())
                connection.cursor.assert_called_once()
                executor.loader.check_consistent_history.assert_called_once_with(connection)
                executor.migrate.assert_not_called()
                self.assertEqual(manifest.call_args.args[3], module)
                self.assertEqual(manifest.call_args.args[4]['cluster_id'], '123456789')

    def test_release_rejects_wrong_configured_identity_before_connecting(self):
        from django.core.management.base import CommandError
        for key, wrong in (('database_name', 'another_database'), ('hostname', 'other.example.test'),
                ('port', '5433'), ('role', 'other_owner')):
            with self.subTest(key=key), self.migration_environment() as (command, connection, executor, manifest):
                options = self.migration_options()
                options[key] = wrong
                with self.assertRaises(CommandError):
                    command.handle(**options)
                connection.cursor.assert_not_called()
                executor.migrate.assert_not_called()
                manifest.assert_not_called()

    def test_release_rejects_wrong_connected_database_role_or_cluster(self):
        from django.core.management.base import CommandError
        for actual in (('other_database', 'release_owner', '123456789'),
                ('release_synthetic', 'other_owner', '123456789'),
                ('release_synthetic', 'release_owner', '987654321')):
            with self.subTest(actual=actual), self.migration_environment() as (command, connection, executor, manifest):
                connection.cursor.return_value.__enter__.return_value.fetchone.return_value = actual
                with self.assertRaisesMessage(CommandError, 'Connected migration cluster/database/role mismatch'):
                    command.handle(**self.migration_options())
                executor.migrate.assert_not_called()
                manifest.assert_not_called()

    def test_release_rejects_unsupported_settings_and_protected_database_names(self):
        from django.core.management.base import CommandError
        for module in ('config.settings.development', 'config.settings.ci', 'config.settings.acceptance', 'unknown'):
            with self.subTest(module=module), self.migration_environment(module) as (command, connection, executor, manifest):
                with self.assertRaises(CommandError):
                    command.handle(**self.migration_options())
                connection.cursor.assert_not_called()
                executor.migrate.assert_not_called()
        for name in ('dawana_dev', 'dic_2026_demo', 'postgres', 'template0', 'template1', ''):
            with self.subTest(name=name), self.migration_environment() as (command, connection, executor, manifest):
                options = self.migration_options()
                options['database_name'] = name
                with self.assertRaises(CommandError):
                    command.handle(**options)
                connection.cursor.assert_not_called()
                executor.migrate.assert_not_called()

    def test_release_parser_requires_every_explicit_target_identifier(self):
        from django.core.management.base import CommandError
        from .management.commands.release_migrations import Command as ReleaseCommand
        arguments = {'--database-name': 'release_synthetic', '--hostname': 'database.example.test',
            '--port': '5432', '--role': 'release_owner', '--cluster-id': '123456789'}
        parser = ReleaseCommand().create_parser('manage.py', 'release_migrations')
        for missing in arguments:
            values = [value for key, argument in arguments.items() if key != missing for value in (key, argument)]
            with self.subTest(missing=missing), self.assertRaises(CommandError):
                parser.parse_args(values)

    def test_render_release_apply_requires_matching_approval_and_restore_evidence(self):
        import json
        from django.core.management.base import CommandError
        from .management.commands import release_migrations as release
        for approval in (None, {'manifest': {'steps': ['different']}},
                {'manifest': {'steps': ['pending']}, 'approved_by': 'Owner'}):
            with self.subTest(approval=approval), self.migration_environment() as (command, connection, executor, manifest):
                options = self.migration_options()
                options['apply_approved_plan'] = True
                if approval is None:
                    with self.assertRaisesMessage(CommandError, 'An approved manifest is required'):
                        command.handle(**options)
                else:
                    options['approval_file'] = 'synthetic-approval.json'
                    with patch.object(release.Path, 'read_text', return_value=json.dumps(approval)):
                        with self.assertRaisesMessage(CommandError, 'Missing, invalid or mismatched migration approval'):
                            command.handle(**options)
                executor.migrate.assert_not_called()

    def test_exact_target_validation_accepts_only_matching_identity(self):
        config = dict(HOST='database.example.test', PORT='5432', USER='release_owner')
        expected = dict(database='release_synthetic', host='database.example.test', port='5432',
            role='release_owner', cluster_id='123456789')
        actual = dict(database='release_synthetic', role='release_owner', cluster_id='123456789')
        validate_target(config, expected, actual)
        for key in expected:
            changed = {**expected, key: ''}
            with self.subTest(missing=key), self.assertRaises(RuntimeError):
                validate_target(config, changed, actual)

    def test_render_migration_wrapper_forwards_identity_without_application_flags(self):
        source = (Path(__file__).resolve().parents[1] / 'render-migrate.sh').read_text(encoding='utf-8')
        self.assertIn('config.settings.render)', source)
        for variable, flag in (('NAME', '--database-name'), ('HOST', '--hostname'),
                ('PORT', '--port'), ('ROLE', '--role'), ('CLUSTER_ID', '--cluster-id')):
            self.assertIn('$' + '{RELEASE_DATABASE_' + variable + ':?', source)
            self.assertIn(flag + ' "$RELEASE_DATABASE_' + variable + '"', source)
        self.assertNotIn('--apply-approved-plan', source)
        self.assertNotIn('--approval-file', source)
        self.assertNotIn('"$@"', source)
