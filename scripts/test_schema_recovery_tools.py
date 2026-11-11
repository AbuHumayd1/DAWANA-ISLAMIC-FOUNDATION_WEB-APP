"""Synthetic recovery subprocess regressions: no Django, credentials, DB or Docker."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('recovery_tools', ROOT / 'backend/config/github_schema_recovery.py')
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)
PRIVATE = 'postgresql://synthetic_user:PRIVATE_PASSWORD@private-host.invalid/private_db'


class RecoveryToolTests(unittest.TestCase):
    def test_workflow_has_no_automatic_trigger_and_tests_precede_secrets(self):
        workflow = json.loads((ROOT / '.github/workflows/production-schema-recovery.yml').read_text())
        self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
        job = workflow['jobs']['recovery']
        self.assertEqual(job['runs-on'], 'ubuntu-24.04')
        self.assertNotIn('services', job)
        steps = job['steps']
        secrets = next(index for index, step in enumerate(steps) if 'RECOVERY_DJANGO_ENV' in step.get('env', {}))
        for script in ('test_schema_recovery_tools.py', 'test_schema_recovery_native.py'):
            index = next(index for index, step in enumerate(steps) if script in step.get('run', ''))
            self.assertLess(index, secrets)
            self.assertNotIn('env', steps[index])
        self.assertIn('production-initialize', job['environment'])
        self.assertEqual(steps[-1]['if'], 'always()')

    def failure(self, stderr, status=1, name='pg_dump'):
        def run(command, **kwargs):
            self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
            self.assertEqual(kwargs['env']['LC_ALL'], 'C')
            kwargs['stderr'].write(stderr.encode())
            self.stderr_file = kwargs['stderr']
            return subprocess.CompletedProcess(command, status)
        with patch.object(recovery.subprocess, 'run', side_effect=run), self.assertRaises(recovery.ToolFailure) as caught:
            recovery.process(['synthetic-never-executed', PRIVATE], tool_name=name)
        self.assertTrue(self.stderr_file.closed)
        encoded = json.dumps(caught.exception.diagnostic) + str(caught.exception)
        for secret in ('PRIVATE_PASSWORD', 'private-host', 'private_db', PRIVATE):
            self.assertNotIn(secret, encoded)
        self.assertEqual(caught.exception.diagnostic['tool'], name)
        self.assertEqual(caught.exception.diagnostic['exit_status'], status)
        return caught.exception.diagnostic['category']

    def test_pr_validation_is_secret_free_and_runs_both_suites(self):
        workflow = json.loads((ROOT / '.github/workflows/recovery-native-validation.yml').read_text())
        self.assertEqual(set(workflow['on']), {'pull_request'})
        self.assertEqual(workflow['on']['pull_request']['branches'], ['main'])
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertNotIn('secrets.', json.dumps(workflow))
        self.assertNotIn('workflow_dispatch', workflow['on'])
        job = workflow['jobs']['recovery-validation']
        self.assertNotIn('environment', job)
        self.assertNotIn('env', job)
        self.assertNotIn('services', job)
        commands = '\n'.join(step.get('run', '') for step in job['steps'])
        self.assertIn('python -I -B scripts/test_schema_recovery_tools.py', commands)
        self.assertIn('python -I -B scripts/test_schema_recovery_native.py', commands)
        self.assertNotIn('config/github_schema_recovery.py --', commands)
        production = json.loads((ROOT / '.github/workflows/production-schema-recovery.yml').read_text())
        install = 'Install native PostgreSQL 18 and isolated restore account'
        self.assertEqual(next(step for step in job['steps'] if step.get('name') == install),
                         next(step for step in production['jobs']['recovery']['steps'] if step.get('name') == install))

    def test_nonzero_exit_reports_only_allowlisted_categories(self):
        cases = {
            'version_mismatch': 'aborting because of server version mismatch',
            'tls_trust_store': 'root certificate file does not exist',
            'tls_verification': 'SSL error: certificate verify failed',
            'authentication': 'password authentication failed for user',
            'database_permissions': 'permission denied for table',
            'snapshot': 'invalid snapshot identifier',
            'executable_unavailable': 'executable file not found in $PATH',
            'timeout': 'connection timed out',
            'connection': 'could not translate host name',
            'filesystem': 'no space left on device',
            'unclassified': 'unexpected private server diagnostic',
        }
        for expected, message in cases.items():
            with self.subTest(category=expected):
                self.assertEqual(self.failure(message + ' ' + PRIVATE), expected)

    def test_helper_diagnostics_preserve_tool_and_status_without_reflecting_values(self):
        detail = json.dumps(dict(tool='pg_restore', exit_status=1, category='database_permissions'))
        def run(command, **kwargs):
            kwargs['stderr'].write(detail.encode())
            return subprocess.CompletedProcess(command, 1)
        with patch.object(recovery.subprocess, 'run', side_effect=run), self.assertRaises(recovery.ToolFailure) as caught:
            recovery.process(['synthetic-never-executed'])
        self.assertEqual(caught.exception.diagnostic, dict(tool='pg_restore', exit_status=1, category='database_permissions'))

    def test_process_start_and_timeout_errors_never_reflect_exception_text(self):
        for error, expected in (
            (FileNotFoundError(PRIVATE), 'executable_unavailable'),
            (PermissionError(PRIVATE), 'process_start_failed'),
            (subprocess.TimeoutExpired([PRIVATE], 900, stderr=PRIVATE), 'timeout'),
        ):
            with self.subTest(category=expected), patch.object(recovery.subprocess, 'run', side_effect=error), \
                    self.assertRaises(recovery.ToolFailure) as caught:
                recovery.process(['synthetic-never-executed'], tool_name='pg_dump')
            self.assertEqual(caught.exception.diagnostic, dict(tool='pg_dump', exit_status=None, category=expected))
            self.assertNotIn(PRIVATE, str(caught.exception))

    def test_unknown_labels_are_redacted(self):
        self.assertEqual(recovery.ToolFailure(PRIVATE, PRIVATE, PRIVATE).diagnostic,
                         dict(tool='unknown', exit_status=None, category='unclassified'))

    def test_success_discards_output_and_does_not_change_timeout(self):
        with patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertIsNone(recovery.process(['synthetic-never-executed']))
        self.assertEqual(run.call_args.kwargs['timeout'], 900)
        self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)

    def test_stderr_classification_is_bounded_and_does_not_print(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.failure('x' * 65536 + ' certificate verify failed ' + PRIVATE), 'unclassified')
        self.assertEqual(output.getvalue(), '')

    @patch.dict(os.environ, {'RECOVERY_DJANGO_ENV': PRIVATE, 'PGSERVICE': PRIVATE, 'GH_TOKEN': PRIVATE}, clear=True)
    def test_native_dump_has_explicit_binary_and_does_not_inherit_environment(self):
        env = dict(PGHOST='private-host.invalid', PGDATABASE='private_db', PGPASSWORD='PRIVATE_PASSWORD',
                   PGSSLMODE='verify-full', PGSSLROOTCERT='/synthetic/runner-ca.pem',
                   PGOPTIONS='-c default_transaction_read_only=on', PGCONNECT_TIMEOUT='5')
        with patch.object(recovery, 'process') as process:
            recovery.tool(['pg_dump', '--format=custom', '--snapshot=synthetic', '--file=/tmp/recovery.dump'], env)
        command = process.call_args.args[0]
        self.assertEqual(command[0], '/usr/lib/postgresql/18/bin/pg_dump')
        for key, value in env.items():
            self.assertEqual(process.call_args.kwargs['env'][key], value)
        for key in ('RECOVERY_DJANGO_ENV', 'PGSERVICE', 'GH_TOKEN'):
            self.assertNotIn(key, process.call_args.kwargs['env'])
        self.assertNotIn('PRIVATE_PASSWORD', command)
        self.assertNotIn('private-host.invalid', command)
        self.assertEqual(process.call_args.kwargs['tool_name'], 'pg_dump')

    @patch.dict(os.environ, {'RECOVERY_DJANGO_ENV': PRIVATE, 'PGPASSWORD': PRIVATE, 'GH_TOKEN': PRIVATE}, clear=True)
    def test_restore_worker_runs_as_dedicated_account_with_empty_environment(self):
        receipt = dict(directory='/tmp/dawana-schema-restore-' + 'a' * 32, cluster_id='12345')
        with patch.object(recovery, 'process') as process:
            recovery.native_cluster('restore', receipt)
        command = process.call_args.args[0]
        self.assertEqual(command[:7], ['/usr/bin/sudo', '-n', '-u', 'dawana_restore', '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin'])
        self.assertNotIn(PRIVATE, command)
        self.assertEqual(process.call_args.kwargs['env'], {'PATH': '/usr/bin:/bin'})
        self.assertEqual(process.call_args.kwargs['cwd'], '/tmp')

    def test_arbitrary_or_remote_restore_receipts_are_refused_before_process(self):
        for receipt in (
            dict(directory='/var/lib/postgresql', cluster_id='123'),
            dict(directory='/tmp/dawana-schema-restore-' + 'a'*32 + '/..', cluster_id='123'),
            dict(directory='/tmp/dawana-schema-restore-' + 'a'*32, cluster_id=PRIVATE),
            dict(directory='/tmp/dawana-schema-restore-' + 'a'*32, cluster_id='123', host='production.invalid'),
        ):
            with self.subTest(receipt=receipt), patch.object(recovery, 'process') as process, self.assertRaises(recovery.Stop):
                recovery.native_cluster('restore', receipt)
            process.assert_not_called()

    def test_unexpected_native_tool_is_refused(self):
        with patch.object(recovery, 'process') as process, self.assertRaises(recovery.Stop):
            recovery.tool(['psql', '--host=production.invalid'], {})
        process.assert_not_called()

    def test_actual_process_receives_no_inherited_secrets(self):
        with patch.dict(os.environ, {'PGPASSWORD': PRIVATE, 'RECOVERY_DJANGO_ENV': PRIVATE}, clear=True), \
                patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            recovery.process(['synthetic-never-executed'])
        self.assertEqual(run.call_args.kwargs['env'], {'LC_ALL': 'C'})

    def test_restore_stream_contains_only_roles_and_archive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'synthetic.dump'
            archive.write_bytes(b'synthetic archive')
            receipt = dict(directory='/tmp/dawana-schema-restore-' + 'a'*32, cluster_id='123')
            def native(action, target, stdin):
                self.assertEqual((action, target), ('restore', receipt))
                self.assertEqual(stdin.read(), b'["synthetic_role"]\nsynthetic archive')
                return b'{"restore_verified":true}'
            with patch.object(recovery, 'native_cluster', side_effect=native):
                recovery.restore_backup(archive, ['synthetic_role'], receipt)

    @patch.dict(os.environ, {'RECOVERY_POSTGRES_MAJOR': '18'}, clear=True)
    def test_matching_client_majors_are_safely_reported(self):
        output = io.StringIO()
        with patch.object(recovery, 'tool', side_effect=[b'pg_dump (PostgreSQL) 18.1 (Debian)',
                b'pg_restore (PostgreSQL) 18.1 (Debian)']) as tool, contextlib.redirect_stdout(output):
            recovery.verify_postgres_clients()
        self.assertEqual(tool.call_args_list[0].args[0], ['pg_dump', '--version'])
        self.assertEqual(tool.call_args_list[1].args[0], ['pg_restore', '--version'])
        self.assertEqual([json.loads(row)['client_major'] for row in output.getvalue().splitlines()], [18, 18])
        self.assertNotIn('Debian', output.getvalue())

    @patch.dict(os.environ, {'RECOVERY_POSTGRES_MAJOR': '18'}, clear=True)
    def test_wrong_or_unknown_client_version_stops_before_production(self):
        for value, expected in ((b'pg_dump (PostgreSQL) 17.7', 'version_mismatch'),
                                (PRIVATE.encode(), 'version_unrecognized')):
            with self.subTest(category=expected), patch.object(recovery, 'tool', return_value=value), \
                    self.assertRaises(recovery.ToolFailure) as caught:
                recovery.verify_postgres_clients()
            self.assertEqual(caught.exception.diagnostic['category'], expected)


if __name__ == '__main__':
    unittest.main()
