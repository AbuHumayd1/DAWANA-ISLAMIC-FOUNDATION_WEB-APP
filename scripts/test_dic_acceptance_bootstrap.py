"""Database-free bootstrap unit tests; no Django setup, subprocesses or DB required."""
import hashlib
from dataclasses import replace
import hmac
import http.client
import os
import smtplib
import socket
import subprocess
import sys
from pathlib import Path
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from acceptance_bootstrap.config import AcceptanceConfig, IsolationError
from acceptance_bootstrap.fixtures import fixture_definitions, validate_fixtures
from acceptance_bootstrap.payments import MockPaystack, MOCK_SECRET
from acceptance_bootstrap.runtime import contained, assert_active


def synthetic_env():
    return {'DIC_ACCEPTANCE_' + k: v for k, v in dict(
        DATABASE='dic_2026_acceptance_' + 'a' * 32, HOST='127.0.0.1', PORT='5432',
        APP_ROLE='acceptance_app', PROVISION_ROLE='acceptance_provisioner',
        PASSWORD='synthetic-not-a-database-credential', SECRET='synthetic-' + 'x' * 64).items()}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.env = synthetic_env()
        self.config = AcceptanceConfig.from_env(self.env)

    def test_valid_explicit_configuration(self):
        self.assertEqual(self.config.host, '127.0.0.1')
        self.assertNotIn(self.config.password, repr(self.config))
        with self.assertRaises(IsolationError): replace(self.config,database='dic_2026_demo')

    def test_missing_configuration(self):
        for key in self.env:
            with self.subTest(key=key), self.assertRaises(IsolationError):
                AcceptanceConfig.from_env({k:v for k,v in self.env.items() if k != key})

    def test_protected_and_malformed_names(self):
        for value in ('dawana_dev', 'dic_2026_demo', 'production', 'dic_2026_acceptance_prod', 'dic_2026_acceptance_' + 'a'*32 + ';DROP'):
            with self.subTest(value=value), self.assertRaises(IsolationError):
                AcceptanceConfig.from_env({**self.env, 'DIC_ACCEPTANCE_DATABASE': value})

    def test_remote_hosts_and_ports(self):
        for key, values in [('HOST', ['localhost', '::1', 'remote.example', '127.0.0.1,remote']), ('PORT', ['0', '65536', '5432;DROP', ''])]:
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(IsolationError):
                    AcceptanceConfig.from_env({**self.env, 'DIC_ACCEPTANCE_' + key: value})

    def test_ambient_urls_and_libpq_rejected_without_secret_output(self):
        for key in ('DATABASE_URL', 'PGSERVICE', 'PGHOST', 'PGPASSFILE', 'PGPASSWORD', 'PGOPTIONS'):
            with self.subTest(key=key), self.assertRaises(IsolationError) as error:
                AcceptanceConfig.from_env({**self.env, key:'postgresql://sensitive@example.test/private'})
            self.assertNotIn('sensitive', str(error.exception))

    def test_unsafe_roles(self):
        for app in ('postgres', 'dawana_app', 'production_reader', 'acceptance_provisioner', 'role;DROP'):
            with self.subTest(app=app), self.assertRaises(IsolationError):
                AcceptanceConfig.from_env({**self.env, 'DIC_ACCEPTANCE_APP_ROLE': app})

    def identity(self):
        return dict(database=self.config.database, host=self.config.host, port=self.config.port,
            role=self.config.app_role, superuser=False, createrole=False, createdb=False)

    def test_identity_and_privilege_guards(self):
        self.config.check_identity(self.identity())
        for key, value in [('database','dic_2026_demo'), ('host','remote'), ('port',5433), ('role','postgres'), ('superuser',True), ('createdb',True), ('createrole',True)]:
            with self.subTest(key=key), self.assertRaises(IsolationError):
                self.config.check_identity({**self.identity(),key:value})
        provision={**self.identity(),'role':self.config.provision_role,'createdb':True}
        self.config.check_identity(provision,provisioning=True)
        with self.assertRaises(IsolationError): self.config.check_identity({**provision,'createdb':False},provisioning=True)

    def test_existing_database_protection(self):
        self.config.check_unused(['dawana_dev', 'dic_2026_demo'])
        with self.assertRaises(IsolationError): self.config.check_unused([self.config.database])

    def test_migration_target_requires_ownership_evidence(self):
        receipt = dict(database=self.config.database, host=self.config.host, port=self.config.port,
            owner=self.config.app_role, created_by=self.config.provision_role, run_id='a'*32, newly_created=True)
        self.config.check_write_target(self.config.database, self.identity(), receipt)
        for key in receipt:
            with self.subTest(key=key), self.assertRaises(IsolationError):
                self.config.check_write_target(self.config.database,self.identity(),{k:v for k,v in receipt.items() if k!=key})
        with self.assertRaises(IsolationError): self.config.check_write_target('dawana_dev', self.identity(), receipt)

    def initialized(self, scenario='success', amount=100000):
        gateway = MockPaystack(); gateway.select('synthetic_ref', scenario)
        gateway.request('POST','/transaction/initialize', dict(reference='synthetic_ref', amount=amount,
            currency='NGN', email='guardian@example.test', metadata={'campers':['minor_a','minor_b']}))
        return gateway

    def test_payment_scenarios_and_grouped_total(self):
        for scenario in MockPaystack.scenarios:
            gateway=self.initialized(scenario)
            data=gateway.request('GET','/transaction/verify/synthetic_ref')['data']
            self.assertEqual(data['status'],MockPaystack.scenarios[scenario])
            self.assertEqual(data['amount'],100001 if scenario=='wrong_amount' else 100000)
            self.assertEqual(data['metadata']['campers'],['minor_a','minor_b'])
            self.assertEqual(data['domain'],'test')

    def test_duplicate_callback_and_signed_webhook_evidence(self):
        gateway=self.initialized()
        self.assertEqual(gateway.request('GET','/transaction/verify/synthetic_ref'),gateway.request('GET','/transaction/verify/synthetic_ref'))
        body, signature=gateway.webhook('synthetic_ref')
        self.assertEqual((body,signature),gateway.webhook('synthetic_ref'))
        self.assertTrue(hmac.compare_digest(signature,hmac.new(MOCK_SECRET.encode(),body,hashlib.sha512).hexdigest()))
        # Database settlement/callback/webhook idempotency still needs E2E tests.

    def test_unmocked_payments_and_real_contacts_blocked(self):
        gateway=MockPaystack()
        with self.assertRaises(IsolationError): gateway.request('POST','/refund',{})
        with self.assertRaises(IsolationError): gateway.request('GET','/transaction/verify/unknown')
        with self.assertRaises(IsolationError): gateway.request('POST','/transaction/initialize',dict(reference='ref',amount=1,currency='NGN',email='real@example.com'))

    def test_network_and_process_blocking_and_restoration(self):
        original=socket.socket.connect
        with contained(self.config):
            assert_active(self.config)
            for action in (lambda:socket.create_connection(('127.0.0.1',5432)),
                    lambda:socket.getaddrinfo('api.paystack.co',443),
                    lambda:urllib.request.urlopen('https://api.paystack.co'),
                    lambda:http.client.HTTPSConnection('api.paystack.co').connect(),
                    lambda:smtplib.SMTP('smtp.example.test'), lambda:subprocess.Popen(['psql'])):
                with self.assertRaises(IsolationError): action()
        self.assertIs(socket.socket.connect, original)
        with self.assertRaises(IsolationError): assert_active(self.config)

    def test_fixture_integrity_and_no_invented_classes(self):
        definitions=fixture_definitions(); self.assertTrue(validate_fixtures(definitions))
        self.assertEqual(definitions['academic_classes'],[])
        definitions['people'][0]['email']='real@example.com'
        with self.assertRaises(IsolationError): validate_fixtures(definitions)
        self.assertTrue(validate_fixtures(fixture_definitions()))

    def test_fixture_relationship_and_privilege_rejection(self):
        for edit in ('guardian','superuser','timetable'):
            data=fixture_definitions()
            if edit=='guardian': data['people'][2]['guardian']='nonexistent'
            elif edit=='superuser': data['accounts'][0]['is_superuser']=True
            else: data['timetables'][0]['description']='Imported real source activity'
            with self.assertRaises(IsolationError): validate_fixtures(data)


if __name__ == '__main__':
    unittest.main()
