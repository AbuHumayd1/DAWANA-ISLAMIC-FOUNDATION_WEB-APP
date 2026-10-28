"""Standard-library regression tests. No Django setup, sockets or database calls."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

spec = importlib.util.spec_from_file_location('finance_validation_helper', Path(__file__).with_name('validate_dic_finance.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class FinanceIdentityTests(unittest.TestCase):
    name = 'test_dic_finance_20261025223457_c8e898d0'

    def connection(self, name=None, address='127.0.0.1', port=5432):
        cursor = MagicMock()
        # Model PostgreSQL's different representations, so reverting to the
        # inet-to-text cast fails the valid IPv4/IPv6 regression cases.
        def execute(sql):
            observed = address
            if 'inet_server_addr()::text' in sql:
                observed += '/128' if ':' in address else '/32'
            cursor.fetchone.return_value = (name or self.name, observed, port)
        cursor.execute.side_effect = execute
        manager = MagicMock()
        manager.__enter__.return_value = cursor
        return SimpleNamespace(cursor=lambda: manager, settings_dict={'PORT': '5432'})

    def test_valid_ipv4_uses_host_representation(self):
        helper.verify_connection_identity(self.name, self.connection())

    def test_valid_ipv6_uses_host_representation(self):
        helper.verify_connection_identity(self.name, self.connection(address='::1'))

    def test_unexpected_or_protected_database_is_rejected(self):
        for name in ['dawana_dev', 'test_dic_portal_2026_local', 'another_database']:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'Unexpected database'):
                helper.verify_connection_identity(self.name, self.connection(name=name))

    def test_remote_or_missing_server_address_is_rejected(self):
        for address in ['192.0.2.10', 'localhost', None]:
            with self.subTest(address=address), self.assertRaisesRegex(RuntimeError, 'Unexpected server address'):
                helper.verify_connection_identity(self.name, self.connection(address=address))

    def test_unexpected_port_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unexpected server port'):
            helper.verify_connection_identity(self.name, self.connection(port=5433))


if __name__ == '__main__':
    unittest.main(verbosity=2)
