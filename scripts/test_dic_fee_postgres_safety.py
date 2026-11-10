"""Database-free guard checks: python -m unittest discover -s scripts -p test_dic_fee_postgres_safety.py"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import dic_fee_postgres as isolation


class IsolationTests(unittest.TestCase):
    def test_loopback_addresses(self):
        for address in ('127.0.0.1', '127.0.0.2', '::1', '0:0:0:0:0:0:0:1', '::ffff:127.0.0.1'):
            with self.subTest(address=address):
                self.assertTrue(isolation.loopback_address(address))
        for address in (None, '', 'localhost', '0.0.0.0', '192.168.1.1', '::', '::ffff:192.168.1.1'):
            with self.subTest(address=address):
                self.assertFalse(isolation.loopback_address(address))

    def test_identity_uses_host_address_not_inet_cast_text(self):
        conn = Mock()
        row = ('postgres', 'synthetic', 5, '127.0.0.1/32', 5433, '170000',
               'synthetic-cluster', '127.0.0.1', '127.0.0.1', 50000)
        conn.execute.return_value.fetchone.return_value = row
        with patch('builtins.print'):
            identity = isolation.identity(conn)
        self.assertEqual(identity['address'], '127.0.0.1')
        for server, client in [('192.168.1.1', '127.0.0.1'), ('127.0.0.1', '192.168.1.1'), (None, None)]:
            conn.execute.return_value.fetchone.return_value = row[:7] + (server, client, 50000)
            with self.subTest(server=server, client=client), patch('builtins.print'), self.assertRaises(RuntimeError):
                isolation.identity(conn)

    def receipt(self):
        return dict(database='test_dic_fees_20261104000000_0123456789ab', host='127.0.0.1',
            port=5432, user='synthetic', marker='a' * 32,
            identity={'maintenance_oid': 5}, baseline_oids=[5, 25041], oid=40000, status='created')

    def test_rejects_protected_or_non_unique_names_and_non_loopback_hosts(self):
        for override in [dict(database='dic_2026_demo'), dict(database='postgres'),
                         dict(database='test_dic_fees_existing'), dict(host='example.test'),
                         dict(identity={'maintenance_oid': 25041})]:
            with self.subTest(override=override), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'plan.json'
                path.write_text(json.dumps(self.receipt() | override), encoding='utf-8')
                with self.assertRaises(RuntimeError): isolation.load(path)

    def test_refuses_receipt_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            isolation.save_new(path, self.receipt())
            with self.assertRaises(FileExistsError): isolation.save_new(path, {})

    @patch.object(isolation, 'verify_server')
    @patch.object(isolation, 'database_info')
    def test_cleanup_identity_checks(self, info, server):
        receipt = self.receipt()
        expected = (40000, 'synthetic', 'dic-fee-test:' + 'a' * 32)
        info.return_value = expected
        isolation.verify_created(object(), receipt)
        for row in [None, (40001, expected[1], expected[2]),
                    (40000, 'other_owner', expected[2]), (40000, 'synthetic', 'other_marker')]:
            info.return_value = row
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                isolation.verify_created(object(), receipt)
        info.return_value = expected
        for override in [dict(oid=25041), dict(oid=5), dict(status='reserved')]:
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                isolation.verify_created(object(), receipt | override)


if __name__ == '__main__':
    unittest.main()
