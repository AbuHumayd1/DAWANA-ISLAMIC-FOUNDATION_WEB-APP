"""Database-free tests of the acceptance runner itself; stdlib imports only."""
import importlib.util
from pathlib import Path
import tempfile
import sys
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch

spec = importlib.util.spec_from_file_location('phase3_acceptance', Path(__file__).with_name('validate_dic_phase3_acceptance.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AcceptanceGuardTests(unittest.TestCase):
    def test_options_failure_operations_are_fixed_sanitized_categories(self):
        for stage in ('options_django', 'options_wsgi_response', 'options_postprocessing'):
            receipt = {}
            result = runner.record_browser_failure(receipt, stage, AttributeError('private-setting-or-response'))
            self.assertEqual(result['stage'], stage)
            self.assertEqual(result['category'], 'attribute_error')
            self.assertNotIn('private-', str(receipt))

    def test_otp_probe_retains_only_allowlisted_boolean_state(self):
        result = runner.safe_otp_probe({'email_option_present': True, 'email_option_enabled': False,
            'email_channel_selected': True, 'reference_valid': True, 'contact_valid': 'private-email',
            'button_disabled': True, 'password': 'private-secret', 'code': 'private-code'})
        self.assertEqual(result, {'email_option_present': True, 'email_option_enabled': False,
            'email_channel_selected': True, 'reference_valid': True, 'button_disabled': True})
        self.assertNotIn('private-', str(result))

    def test_browser_diagnostics_never_retain_exception_messages_or_unknown_stages(self):
        fake_timeout = type('TimeoutError', (Exception,), {'__module__': 'playwright._impl._errors'})
        fake_error = type('Error', (Exception,), {'__module__': 'playwright._impl._errors'})
        for error, category, hint in ((fake_timeout('private-password-and-otp'), 'playwright_timeout', 'operation_timed_out'),
                (fake_error('strict mode violation private-token'), 'playwright_error', 'locator_ambiguous'),
                (KeyError('private-email'), 'key_error', 'inspect_failed_stage')):
            receipt = {}
            diagnostic = runner.record_browser_failure(receipt, 'booking_contact', error)
            self.assertEqual(diagnostic, {'stage': 'booking_contact', 'category': category, 'hint': hint})
            self.assertNotIn('private-', str(receipt))
        self.assertEqual(runner.safe_browser_failure('private-path', Exception('private-secret'))['stage'], 'unknown')

    def test_internal_socketpair_works_without_allowing_arbitrary_connect(self):
        pair = runner.make_loopback_socketpair(socket.socket.connect)
        with patch.object(socket.socket, 'connect', runner.denied):
            server, client = pair()
            try:
                client.sendall(b'wakeup')
                server.settimeout(2)
                self.assertEqual(server.recv(6), b'wakeup')
                with socket.socket() as other:
                    with self.assertRaises(runner.StopAcceptance): other.connect(('127.0.0.1', 12345))
            finally:
                server.close(); client.close()
            if sys.platform == 'win32':
                import asyncio
                with patch.object(socket, 'socketpair', pair):
                    loop = asyncio.ProactorEventLoop()
                    try:
                        self.assertEqual(loop.run_until_complete(asyncio.sleep(0, result='ready')), 'ready')
                    finally:
                        loop.close()
        with self.assertRaises(runner.StopAcceptance): pair(type=socket.SOCK_DGRAM)

    def test_browser_prerequisite_errors_identify_each_missing_requirement(self):
        for flags, expected in (({'frontend_build': True, 'playwright_package': False}, 'Python Playwright'),
                ({'frontend_build': False, 'playwright_package': True}, 'frontend build')):
            with self.subTest(flags=flags), self.assertRaisesRegex(runner.StopAcceptance, expected):
                runner.require_browser_prerequisites(flags)
        runner.require_browser_prerequisites({'frontend_build': True, 'playwright_package': True})

    def test_mock_provider_transaction_id_is_positive_integer_and_stable(self):
        scenario = runner.Scenario('a'*32)
        scenario.initialize(None, email=scenario.owner, reference='synthetic-reference', amount_kobo=1250000)
        fake_timezone = SimpleNamespace(now=lambda: SimpleNamespace(isoformat=lambda: 'synthetic-time'))
        with patch.dict(sys.modules, {'django': Mock(), 'django.utils': SimpleNamespace(timezone=fake_timezone)}):
            first = scenario.verify(None, 'synthetic-reference')
            second = scenario.verify(None, 'synthetic-reference')
        self.assertIs(type(first['id']), int)
        self.assertTrue(0 < first['id'] < 10**64)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['domain'], 'test')
        self.assertEqual(first['amount'], 1250000)

    def test_identity_uses_host_without_mask_and_retains_all_strict_comparisons(self):
        connection = Mock()
        connection.settings_dict = {'NAME': runner.DATABASE}
        connection.cursor.return_value = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (runner.DATABASE, '127.0.0.1', 5432, 'on')
        self.assertEqual(runner.identity(connection, 5432, readonly=True)['host'], '127.0.0.1')
        self.assertIn('host(inet_server_addr())', cursor.execute.call_args.args[0])
        for row in (('unapproved', '127.0.0.1', 5432, 'on'),
                (runner.DATABASE, '192.0.2.1', 5432, 'on'),
                (runner.DATABASE, '127.0.0.1', 5433, 'on'),
                (runner.DATABASE, '127.0.0.1', 5432, 'off')):
            with self.subTest(row=row):
                cursor.fetchone.return_value = row
                with self.assertRaises(runner.StopAcceptance): runner.identity(connection, 5432, readonly=True)
        connection.settings_dict['NAME'] = 'unapproved'
        with self.assertRaises(runner.StopAcceptance): runner.identity(connection, 5432)

    def test_writing_modes_refuse_without_confirmation_before_configure(self):
        for command in ('integration', 'browser'):
            with self.subTest(command=command), patch('sys.argv', ['runner', command, '--database', 'dic_2026_demo']), patch.object(runner, 'configure') as configure:
                with self.assertRaises(runner.StopAcceptance): runner.main()
                configure.assert_not_called()

    def test_database_is_required_and_other_names_are_refused(self):
        for arguments in (['preflight'], ['preflight', '--database', 'unapproved_database']):
            with self.subTest(arguments=arguments), patch('sys.argv', ['runner', *arguments]), patch.object(runner, 'configure') as configure:
                with self.assertRaises(SystemExit): runner.main()
                configure.assert_not_called()

    def inventory(self):
        inventory = object.__new__(runner.Inventory)
        inventory.keys = {'dic_example': 'id'}
        inventory.baseline = {'dic_example': {'1'}}
        inventory.owned = {'dic_example': {'2'}}
        inventory.ids = Mock(return_value={'2'})
        return inventory

    def test_destructive_unrecognized_and_multistatement_sql_is_refused(self):
        for sql in ('DELETE FROM "dic_example"', 'DROP TABLE "dic_example"', 'TRUNCATE "dic_example"',
                'CREATE TABLE x (id int)', 'ALTER TABLE x ADD y int', 'COMMIT', 'DO $$ BEGIN END $$',
                'SET x=1; DELETE FROM "dic_example"', 'SELECT 1 -- hidden statement',
                'UPDATE "dic_example" SET x=%s', 'INSERT INTO "django_migrations" (x) VALUES (%s)'):
            with self.subTest(sql=sql):
                execute = Mock()
                with self.assertRaises(runner.StopAcceptance): self.inventory()(execute, sql, (0,), False, {})
                execute.assert_not_called()

    def test_update_of_preexisting_rows_is_refused(self):
        inventory = self.inventory(); inventory.ids.return_value = {'1', '2'}
        execute = Mock()
        with self.assertRaises(runner.StopAcceptance):
            inventory(execute, 'UPDATE "dic_example" SET "x"=%s WHERE "id"=%s', ('synthetic', 1), False, {})
        execute.assert_not_called()

    def test_owned_update_checks_only_where_parameters(self):
        inventory = self.inventory(); execute = Mock(return_value='ok')
        result = inventory(execute, 'UPDATE "dic_example" SET "x"=%s WHERE "id"=%s', ('synthetic', 2), False, {})
        self.assertEqual(result, 'ok')
        inventory.ids.assert_called_once_with('dic_example', '"id"=%s', (2,))
        execute.assert_called_once()

    def test_insert_tracks_only_rows_absent_from_baseline(self):
        inventory = self.inventory(); inventory.ids.return_value = {'1', '2', '3'}
        inventory(Mock(), 'INSERT INTO "dic_example" ("x") VALUES (%s)', ('synthetic',), False, {})
        self.assertEqual(inventory.owned['dic_example'], {'2', '3'})

    def test_receipts_cannot_be_written_outside_the_acceptance_directory(self):
        with self.assertRaises(runner.StopAcceptance): runner.write_receipt(Path('outside.json'), {})
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'RECEIPTS', Path(directory)):
            path = Path(directory)/'receipt.json'
            runner.write_receipt(path, {'fixtures': {}, 'cleanup': 'no_database_writes'})
            self.assertIn('no_database_writes', path.read_text())


if __name__ == '__main__':
    unittest.main()
