"""Standard-library unit tests: fake tools/storage only; never connect to PostgreSQL."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch, Mock
import dic_backup_readiness as b


class BackupReadinessTests(unittest.TestCase):
    def test_only_exact_demo_loopback_target(self):
        b.target_guard('dic_2026_demo', '127.0.0.1', '5432', 'demo_reader')
        for database, host, port in [('dawana_dev','127.0.0.1','5432'), ('production','127.0.0.1','5432'),
                ('dic_2026_demo','localhost','5432'), ('dic_2026_demo','remote.example','5432'),
                ('dic_2026_demo','127.0.0.1,remote','5432'), ('dic_2026_demo','127.0.0.1','5433')]:
            with self.subTest(database=database, host=host, port=port), self.assertRaises(b.ReadinessError):
                b.target_guard(database, host, port, 'reader')

    def test_role_cannot_be_connection_string_or_option(self):
        for role in ['', '--host=remote', 'postgresql://secret@remote/db', 'a b']:
            with self.assertRaises(b.ReadinessError): b.target_guard(b.DATABASE, '127.0.0.1', '5432', role)

    def test_restore_protected_names_rejected(self):
        for name in ['dic_2026_demo','dawana_dev','postgres','production','test_demo','dic_2026_restore_', 'dic_2026_restore_123456789abc;DROP DATABASE x']:
            with self.subTest(name=name), self.assertRaises(b.ReadinessError): b.restore_guard(name)
        b.restore_guard('dic_2026_restore_123456abcdef')

    def test_destination_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'PRIVATE', Path(folder)):
            path = Path(folder) / 'new.dump'
            b.destination_guard(path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])
            for bad in [Path(folder), Path(folder) / 'missing/new.dump', Path(folder).parent / 'outside.dump']:
                with self.assertRaises(b.ReadinessError): b.destination_guard(bad)

    def test_existing_archive_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'PRIVATE', Path(folder)):
            path = Path(folder) / 'old.dump'; path.write_bytes(b'unchanged')
            with self.assertRaises(b.ReadinessError): b.destination_guard(path)
            self.assertEqual(path.read_bytes(), b'unchanged')

    def test_missing_explicit_tools_never_fall_back(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(b.shutil, 'which') as which:
            with self.assertRaises(b.ReadinessError): b.find_tools(bin_dir=folder)
            which.assert_not_called()

    def test_explicit_toolset_and_individual_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            suffix = '.exe' if os.name == 'nt' else ''
            paths = {name: Path(folder) / (name + suffix) for name in b.TOOLS}
            for path in paths.values(): path.touch()
            self.assertEqual(set(b.find_tools(bin_dir=folder)), set(b.TOOLS))
            self.assertEqual(b.find_tools({k: str(v) for k,v in paths.items()})['psql'], str(paths['psql'].resolve()))

    def test_inherited_libpq_and_application_secrets_removed(self):
        with patch.dict(os.environ, {'PGHOST':'remote', 'PGDATABASE':'production', 'PGSERVICE':'production',
                'PGOPTIONS':'-c default_transaction_read_only=off', 'PGPASSWORD':'old-secret',
                'DATABASE_URL':'postgresql://secret@remote/prod','PAYSTACK_SECRET_KEY':'key',
                'DIC_DEMO_PG_PASSWORD':'explicit-secret'}):
            env = b.child_environment('DIC_DEMO_PG_PASSWORD')
        self.assertEqual(env['PGPASSWORD'], 'explicit-secret')
        self.assertNotIn('PGHOST', env); self.assertNotIn('PGSERVICE', env)
        self.assertNotIn('DATABASE_URL', env); self.assertNotIn('PAYSTACK_SECRET_KEY', env)
        self.assertIn('default_transaction_read_only=on', env['PGOPTIONS'])

    def test_missing_password_variable_and_ambiguous_credentials_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(b.ReadinessError): b.child_environment('MISSING')
        with self.assertRaises(b.ReadinessError): b.child_environment('PASSWORD', '/passfile')

    def test_write_commands_rejected_before_process_start(self):
        runner = Mock()
        for command in [['pg_dump','--dbname',b.DATABASE], ['pg_restore','--dbname',b.DATABASE,'a.dump'],
                ['pg_restore','--clean','a.dump'], ['psql','--command','CREATE DATABASE test'],
                ['psql','--file','script.sql']]:
            with self.subTest(command=command), self.assertRaises(b.ReadinessError): b.run_read(command, {}, runner)
        runner.assert_not_called()

    def test_fixed_identity_command_requires_readonly_environment(self):
        env = b.child_environment(); env['DIC_READINESS_USER'] = 'reader'
        runner = Mock(return_value=NS(returncode=0, stdout='safe'))
        b.run_read(['psql', *b.connection_args('reader')], env, runner)
        passed = runner.call_args.kwargs['env']
        self.assertIn('default_transaction_read_only=on', passed['PGOPTIONS'])
        self.assertNotIn('DIC_READINESS_USER', passed)
        self.assertIn('--no-psqlrc', runner.call_args.args[0])
        with self.assertRaises(b.ReadinessError):
            b.run_read(['psql', *b.connection_args('reader')], {'DIC_READINESS_USER':'reader'}, runner)

    def test_diagnostics_never_echo_secrets(self):
        runner = Mock(return_value=NS(returncode=1, stdout='postgresql://password@host/db', stderr='secret-token'))
        with self.assertRaises(b.ReadinessError) as caught: b.run_read(['psql','--version'], {}, runner)
        self.assertNotIn('password@', str(caught.exception)); self.assertNotIn('secret-token', str(caught.exception))
        self.assertNotIn('example-secret', b.redact('postgresql://u:example-secret@host/db password=example-secret', ['example-secret']))

    def test_timeout_and_missing_executable_fail_closed(self):
        for error in [OSError('secret'), subprocess.TimeoutExpired('secret', 1)]:
            with self.assertRaises(b.ReadinessError) as caught:
                b.run_read(['psql','--version'], {}, Mock(side_effect=error))
            self.assertNotIn('secret', str(caught.exception))

    def test_version_mismatch_and_untrusted_output_rejected(self):
        tools = {n: n for n in b.TOOLS}
        with patch.object(b, 'run_read', side_effect=['pg_dump (PostgreSQL) 17.5','pg_restore (PostgreSQL) 18.0','psql (PostgreSQL) 17.5']):
            with self.assertRaises(b.ReadinessError): b.versions(tools, {})
        with patch.object(b, 'run_read', return_value='secret arbitrary text'):
            with self.assertRaises(b.ReadinessError): b.versions(tools, {})

    def test_connection_identity_readonly_and_version_failures(self):
        for row in ['dawana_dev|127.0.0.1|5432|on|170005|reader|100|0|0|0|0',
                'dic_2026_demo|127.0.0.1|5432|off|170005|reader|100|0|0|0|0',
                'dic_2026_demo|127.0.0.1|5432|on|180000|reader|100|0|0|0|0',
                'dic_2026_demo|127.0.0.1|5432|on|170005|other|100|0|0|0|0',
                'dic_2026_demo|127.0.0.1|5432|on|170005|reader|100|1|0|0|0',
                'dic_2026_demo|127.0.0.1|5432|on|170005|reader|100|0|0|1|0']:
            with patch.object(b, 'run_read', return_value=row), self.assertRaises(b.ReadinessError):
                b.verify_connection({'psql':'psql'}, {}, 'reader', 17, 2**40)
        with patch.object(b, 'run_read', return_value='dic_2026_demo|127.0.0.1|5432|on|170005|reader|100|0|0|0|0'):
            self.assertTrue(b.verify_connection({'psql':'psql'}, {}, 'reader', 17, 2**40)['transaction_read_only'])
            with self.assertRaises(b.ReadinessError): b.verify_connection({'psql':'psql'}, {}, 'reader', 17, 1)

    def test_receipt_unchanged_and_archives_require_hash(self):
        self.assertEqual(b.receipt_check(), b.RECEIPT_SHA256)
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'PRIVATE', Path(folder)):
            archive = Path(folder) / 'test.dump'; archive.write_bytes(b'PGDMPfake')
            with self.assertRaises(b.ReadinessError): b.verify_archive({}, {}, archive, '')
            with self.assertRaises(b.ReadinessError): b.verify_archive({}, {}, archive, '0' * 64)

    def test_archive_identity_and_full_read_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'PRIVATE', Path(folder)):
            archive = Path(folder) / 'test.dump'; archive.write_bytes(b'PGDMPfake')
            sha = b.hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(b, 'run_read', return_value='; dbname: dawana_dev\n1; table'):
                with self.assertRaises(b.ReadinessError): b.verify_archive({'pg_restore':'pg_restore'}, {}, archive, sha)
            with patch.object(b, 'run_read', side_effect=['; dbname: dic_2026_demo\n1; table', b.ReadinessError('read failed')]):
                with self.assertRaises(b.ReadinessError): b.verify_archive({'pg_restore':'pg_restore'}, {}, archive, sha)
            with patch.object(b, 'run_read', side_effect=['; dbname: dic_2026_demo\n1; table', '']) as run:
                result = b.verify_archive({'pg_restore':'pg_restore'}, {}, archive, sha)
                self.assertTrue(result['toc_and_full_read'])
                self.assertFalse(result['restore_rehearsed'])
                self.assertTrue(all('--dbname' not in call.args[0] for call in run.call_args_list))

    def test_default_preflight_cannot_connect_dump_or_restore(self):
        tools = {n:n for n in b.TOOLS}
        with patch.object(b, 'destination_guard', return_value=(Path('/private/new.dump'), 2**40)), patch.object(b, 'find_tools', return_value=tools), patch.object(b, 'versions', return_value={n:(17,5) for n in tools}), patch.object(b, 'verify_connection') as connect, patch.object(b, 'verify_archive') as archive, patch.object(b, 'run_read') as run, redirect_stdout(StringIO()):
            self.assertEqual(b.main(['--username','reader']), 0)
            connect.assert_not_called(); archive.assert_not_called(); run.assert_not_called()

    def test_failures_have_nonzero_exit_without_raw_output(self):
        output = StringIO()
        with patch.object(b, 'receipt_check', side_effect=OSError('secret-url')), redirect_stderr(output):
            self.assertEqual(b.main(['--username','reader']), 1)
        self.assertNotIn('secret-url', output.getvalue())
        for option in ('--password', '--password-e'):
            output = StringIO()
            with self.subTest(option=option), redirect_stderr(output), self.assertRaises(SystemExit) as caught:
                b.main([option, 'postgresql://secret@remote/prod'])
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn('secret@', output.getvalue())


if __name__ == '__main__':
    unittest.main()
