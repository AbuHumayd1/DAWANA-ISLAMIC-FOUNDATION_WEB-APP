"""Synthetic-only guard tests; no production settings, secrets or connections."""
import base64
import contextlib
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from config import phase_a_migration_build as build
from config.release_migrations import plan_manifest


class MigrationBuildTests(unittest.TestCase):
    def setUp(self):
        from django.conf import settings
        if not settings.configured:
            settings.configure(AUTH_USER_MODEL='accounts.User')
        module = importlib.import_module('dic.migrations.0041_phase_a_order_lifecycle')
        self.migration = module.Migration(build.TARGET[1], 'dic')
        self.identity = dict(database='synthetic_prod', host='db.example.test', port='5432',
                             role='synthetic_role', cluster_id='12345')
        self.env = {'RENDER': 'true', 'RENDER_GIT_COMMIT': 'a' * 40, 'DAWANA_PHASE_A_MODE': 'plan',
                    **{'DAWANA_PHASE_A_' + k.upper(): v for k, v in self.identity.items()}}
        self.ca = tempfile.TemporaryDirectory()
        self.addCleanup(self.ca.cleanup)
        root = Path(self.ca.name) / 'ca.pem'
        root.write_text('synthetic; no connection is ever opened')
        self.connection = MagicMock()
        self.connection.settings_dict = dict(ENGINE='django.db.backends.postgresql', NAME='synthetic_prod',
            HOST='db.example.test', PORT='5432', USER='synthetic_role',
            OPTIONS=dict(sslmode='verify-full', sslrootcert=str(root)))
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.side_effect = [
            (True,), ('synthetic_prod', 'synthetic_role', '12345'), (True,)]
        self.executor = Mock(connection=self.connection)
        self.executor.loader.detect_conflicts.return_value = {}
        self.executor.loader.graph.nodes = {build.TARGET: self.migration}
        self.executor.loader.graph.leaf_nodes.return_value = [build.TARGET]
        self.executor.migration_plan.return_value = [(self.migration, False)]
        self.refreshed = Mock()
        self.refreshed.migration_plan.return_value = []
        self.refreshed.loader.applied_migrations = {build.TARGET}
        self.factory = Mock(side_effect=[self.executor, self.refreshed])
        self.committed = False
        self.rolled_back = False

        @contextlib.contextmanager
        def atomic(**kwargs):
            try:
                yield
            except BaseException:
                self.rolled_back = True
                raise
            else:
                self.committed = True
        self.transaction = Mock(atomic=atomic)
        manifest = plan_manifest(self.executor.loader, [(self.migration, False)],
                                 'synthetic_prod', 'config.settings.render', self.identity)
        self.approval = dict(manifest=manifest, release_commit='a' * 40,
            approved_by='synthetic reviewer', approved_at='2026-11-13T00:00:00Z',
            backup_reference='synthetic backup', restore_procedure='synthetic restore',
            rollback_decision='retain additive schema')

    def run_build(self, mode='apply', approval=None):
        return build.execute(self.connection, self.transaction, self.factory, mode,
                             self.identity, 'a' * 40, self.approval if approval is None else approval)

    def test_read_only_plan_never_migrates(self):
        result = self.run_build('plan')
        self.assertEqual(result['manifest'], self.approval['manifest'])
        self.executor.migrate.assert_not_called()
        self.cursor.execute.assert_any_call('SET TRANSACTION READ ONLY')

    def test_approved_exact_plan_commits(self):
        self.assertIsNone(self.run_build())
        self.assertTrue(self.committed)
        self.executor.migrate.assert_called_once_with([build.TARGET], plan=[(self.migration, False)])

    def test_wrong_identity_and_missing_cluster_privilege_stop_before_migrate(self):
        for results in ([(True,), ('wrong_db', 'synthetic_role', '12345')],
                        [(True,), ('synthetic_prod', 'wrong_role', '12345')],
                        [(True,), ('synthetic_prod', 'synthetic_role', '99999')]):
            with self.subTest(results=results):
                self.cursor.fetchone.side_effect = results
                with self.assertRaises(build.Stop):
                    self.run_build()
        self.cursor.execute.side_effect = PermissionError('secret driver message')
        with self.assertRaises(PermissionError):
            self.run_build()
        self.executor.migrate.assert_not_called()

    def test_busy_lock_or_non_tls_session_stops(self):
        for results in ([(False,)], [(True,), ('synthetic_prod', 'synthetic_role', '12345'), (False,)]):
            self.cursor.fetchone.side_effect = results
            with self.assertRaises(build.Stop):
                self.run_build()
        self.executor.migrate.assert_not_called()

    def test_other_pending_backward_or_empty_plan_stops(self):
        other = Mock(app_label='auth', name='other')
        for plan in ([], [(other, False)], [(self.migration, True)],
                     [(self.migration, False), (other, False)]):
            self.executor.migration_plan.return_value = plan
            with self.subTest(plan=plan), self.assertRaises(build.Stop):
                build.exact_plan(self.executor)
        self.executor.migrate.assert_not_called()

    def test_graph_conflict_history_and_missing_target_stop(self):
        self.executor.loader.detect_conflicts.return_value = {'dic': ['conflict']}
        with self.assertRaises(build.Stop):
            build.exact_plan(self.executor)
        self.executor.loader.detect_conflicts.return_value = {}
        self.executor.loader.graph.nodes = {}
        with self.assertRaises(build.Stop):
            build.exact_plan(self.executor)
        self.executor.loader.check_consistent_history.side_effect = RuntimeError('inconsistent')
        with self.assertRaises(RuntimeError):
            build.exact_plan(self.executor)

    def test_data_operation_or_non_atomic_migration_rejected(self):
        self.migration.operations.append(Mock())
        with self.assertRaises(build.Stop):
            build.exact_plan(self.executor)
        self.migration.operations.pop()
        self.migration.atomic = False
        with self.assertRaises(build.Stop):
            build.exact_plan(self.executor)

    def test_tls_downgrades_and_endpoint_overrides_rejected(self):
        original = copy.deepcopy(self.connection.settings_dict)
        variants = [dict(sslmode=mode) for mode in ('require', 'prefer', 'disable')]
        variants += [dict(sslrootcert='/missing/ca'), dict(service='other'), dict(hostaddr='127.0.0.1')]
        for variant in variants:
            config = copy.deepcopy(original)
            config['OPTIONS'].update(variant)
            with self.subTest(variant=variant), self.assertRaises(build.Stop):
                build.check_config(config, self.identity)
        for field in ('HOST', 'PORT', 'USER', 'NAME'):
            config = copy.deepcopy(original)
            config[field] = 'wrong'
            with self.subTest(field=field), self.assertRaises(build.Stop):
                build.check_config(config, self.identity)

    def test_approval_source_identity_and_evidence_binding(self):
        for mutate in ('source', 'identity', 'backup', 'missing'):
            approval = copy.deepcopy(self.approval)
            if mutate == 'source':
                approval['manifest']['steps'][0]['source_sha256'] = '0' * 64
            elif mutate == 'identity':
                approval['manifest']['target_identity']['cluster_id'] = '9'
            elif mutate == 'backup':
                approval['backup_reference'] = ''
            else:
                approval = {}
            self.cursor.fetchone.side_effect = [(True,), ('synthetic_prod', 'synthetic_role', '12345'), (True,)]
            self.factory.side_effect = [self.executor, self.refreshed]
            with self.subTest(mutate=mutate), self.assertRaises(build.Stop):
                self.run_build(approval=approval)
        self.executor.migrate.assert_not_called()

    def test_sql_failure_and_postcheck_failure_roll_back(self):
        self.executor.migrate.side_effect = RuntimeError('secret SQL diagnostic')
        with self.assertRaises(RuntimeError):
            self.run_build()
        self.assertTrue(self.rolled_back)
        self.assertFalse(self.committed)
        self.executor.migrate.side_effect = None
        self.factory.side_effect = [self.executor, self.refreshed]
        self.cursor.fetchone.side_effect = [(True,), ('synthetic_prod', 'synthetic_role', '12345'), (True,)]
        self.refreshed.migration_plan.return_value = [(self.migration, False)]
        with self.assertRaises(build.Stop):
            self.run_build()
        self.assertFalse(self.committed)

    def test_explicit_inputs_and_commit_digest_binding(self):
        self.assertEqual(build.inputs(self.env)[:3], ('plan', self.identity, 'a' * 40))
        for field in tuple(self.env):
            env = dict(self.env)
            del env[field]
            with self.subTest(field=field), self.assertRaises(build.Stop):
                build.inputs(env)
        raw = json.dumps(self.approval).encode()
        env = {**self.env, 'DAWANA_PHASE_A_MODE': 'apply',
               'DAWANA_PHASE_A_APPROVAL_B64': base64.b64encode(raw).decode(),
               'DAWANA_PHASE_A_APPROVAL_SHA256': hashlib.sha256(raw).hexdigest()}
        self.assertEqual(build.inputs(env)[3], self.approval)
        for field, value in (('DAWANA_PHASE_A_APPROVAL_B64', 'invalid'),
                             ('DAWANA_PHASE_A_APPROVAL_SHA256', 'wrong'),
                             ('RENDER_GIT_COMMIT', 'b' * 40)):
            with self.subTest(field=field), self.assertRaises(build.Stop):
                build.inputs({**env, field: value})

    def test_failure_logs_do_not_echo_secrets(self):
        output = io.StringIO()
        with patch.object(build, 'inputs', side_effect=RuntimeError('SECRET-password-url')), \
                contextlib.redirect_stderr(output):
            self.assertEqual(build.main(), 1)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertIn('INTERNAL_FAILURE_REVIEW_PRIVATELY', output.getvalue())

    def test_build_wrapper_always_fails_without_starting_web(self):
        text = (ROOT / 'backend/phase-a-migration-build.sh').read_text()
        self.assertTrue(text.rstrip().endswith('exit 1'))
        self.assertNotIn('native-start', text)
        self.assertNotIn('manage.py migrate', text)

    def test_real_shell_refuses_promotion_after_python_success_or_failure(self):
        bash = shutil.which('bash')
        if not bash and Path('C:/Program Files/Git/bin/bash.exe').is_file():
            bash = 'C:/Program Files/Git/bin/bash.exe'
        if not bash:
            self.skipTest('Bash unavailable; CI requires this behavioral check')
        with tempfile.TemporaryDirectory(prefix='phase-a-shell-') as temporary:
            stub = Path(temporary) / 'python'
            for exit_code in (0, 1):
                stub.write_text('#!/bin/sh\necho synthetic-python-invoked\nexit ' + str(exit_code) + '\n',
                                encoding='utf-8', newline='\n')
                stub.chmod(0o700)
                result = subprocess.run([bash, '-c',
                    'export PATH="$1:$PATH"; bash backend/phase-a-migration-build.sh',
                    'synthetic-shell-test', temporary], cwd=ROOT,
                    capture_output=True, text=True, timeout=20)
                with self.subTest(python_exit=exit_code):
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn('synthetic-python-invoked', result.stdout)
                    self.assertIn('COMPLETE:' if exit_code == 0 else 'STOP:', result.stderr)
                    self.assertNotIn('Launching Gunicorn', result.stdout + result.stderr)

    def test_direct_executor_rejects_bad_mode_or_release_before_connecting(self):
        with self.assertRaises(build.Stop):
            self.run_build('unexpected')
        approval = {**self.approval, 'release_commit': 'b' * 40}
        with self.assertRaises(build.Stop):
            self.run_build(approval=approval)
        self.connection.cursor.assert_not_called()
        self.factory.assert_not_called()

    def test_render_settings_keep_live_payment_values_and_require_verified_tls(self):
        # Fresh processes use only explicit SYNTHETIC environment values.
        # Block dotenv, sockets and Django database access before settings load.
        environment = {key: os.environ[key] for key in
                       ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        environment.update(DJANGO_SETTINGS_MODULE='config.settings.render',
            PUBLIC_HOST='backend.example.test', FRONTEND_ORIGIN='https://portal.example.test',
            DJANGO_SECRET_KEY='synthetic-render-migration-only-' * 3,
            DATABASE_URL='postgresql://synthetic_role:unused@db.example.test/synthetic_prod',
            PAYSTACK_MODE='live', PAYSTACK_LIVE_ENABLED='true',
            PAYSTACK_SECRET_KEY='sk_live_SYNTHETIC_NOT_A_CREDENTIAL',
            DB_SSLMODE='verify-full',
            DB_SSLROOTCERT=self.connection.settings_dict['OPTIONS']['sslrootcert'])
        # Local dependency stores may supplement, never replace, runtime packages.
        dependencies = [p for p in sys.path if 'site-packages' in p]
        bootstrap = 'import sys; sys.path.extend(' + repr(dependencies) + '); '
        bootstrap += 'sys.path.insert(0, ' + repr(str(ROOT / 'backend')) + ')\n'
        code = bootstrap + '''
from unittest.mock import patch
import environ
from django.db.backends.base.base import BaseDatabaseWrapper
def denied(*args, **kwargs):
    raise RuntimeError('Network/database forbidden in synthetic settings test')
with patch.object(environ.Env, 'read_env'), patch.object(BaseDatabaseWrapper, 'ensure_connection', denied), patch('socket.socket.connect', denied), patch('socket.create_connection', denied):
    from django.conf import settings
    from config.phase_a_migration_build import check_config
    check_config(settings.DATABASES['default'], dict(database='synthetic_prod', host='db.example.test', port='5432', role='synthetic_role', cluster_id='12345'))
    assert settings.PAYSTACK_MODE == 'live'
    assert settings.PAYSTACK_LIVE_ENABLED is True
    assert settings.PAYSTACK_SECRET_KEY == 'sk_live_SYNTHETIC_NOT_A_CREDENTIAL'
    assert settings.DATABASES['default']['OPTIONS']['sslmode'] == 'verify-full'
print('PASS: synthetic Render settings compatible; LIVE values preserved; no connections')
'''
        for extra, succeeds in (({}, True), ({'DB_SSLMODE': 'require'}, False),
                ({'DB_SSLROOTCERT': '/missing/ca.pem'}, False),
                ({'DATABASE_URL': 'postgresql://synthetic_role:unused@dpg-internal/synthetic_prod'}, False)):
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code],
                                    env={**environment, **extra}, capture_output=True,
                                    text=True, timeout=30)
            with self.subTest(extra=extra):
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                if succeeds:
                    self.assertIn('LIVE values preserved', result.stdout)


if __name__ == '__main__':
    unittest.main()
