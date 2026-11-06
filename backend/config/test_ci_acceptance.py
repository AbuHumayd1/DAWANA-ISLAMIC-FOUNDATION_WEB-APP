"""Database-free checks for CI routing and truthful result accounting."""
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from django.test import SimpleTestCase
from .ci_acceptance import CountedResult, guarded_connections, outcome, partition_for, regression_ids, require_ci, validate_regressions


class AcceptanceHarnessTests(SimpleTestCase):
    def result(self):
        return CountedResult(unittest.runner._WritelnDecorator(StringIO()), True, 0)

    def test_protected_modules_keep_their_existing_database_guards(self):
        for name, partition in [('dic.test_tutor_registration.TutorIntegrationTests.test_case', 'tutor'),
                ('dic.test_registration_privacy.RegistrationPrivacyIntegrationTests.test_case', 'tutor'),
                ('dic_movement.test_integration.MovementIntegrationTests.test_case', 'movement'),
                ('dic_assistance.test_integration.AssistanceIntegrationTests.test_case', 'assistance'),
                ('dic.test_payment_hardening.PaymentEvidenceTests.test_case', 'core')]:
            self.assertEqual(partition_for(name), partition)

    def test_local_invocation_is_refused(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false', 'DAWANA_CI_ACCEPTANCE': '1'}):
            with self.assertRaises(RuntimeError): require_ci()

    def test_all_nine_regressions_are_mandatory(self):
        names = sorted(regression_ids())
        self.assertEqual(len(names), 9)
        validate_regressions(names)
        with self.assertRaises(RuntimeError): validate_regressions(names[:-1])
        with self.assertRaises(RuntimeError):
            validate_regressions(names[:-1] + ['dic.test_production_payments.PaymentEntitlementModeTests.test_invented'])

    def test_only_completed_successes_are_passed(self):
        test = unittest.FunctionTestCase(lambda: None)
        result = self.result()
        result.startTest(test)
        result.addSuccess(test)
        result.stopTest(test)
        report = outcome([test.id()], result)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['passed'], 1)
        self.assertEqual(report['not_started'], 0)

    def test_skipped_and_unexecuted_tests_are_never_passed(self):
        test = unittest.FunctionTestCase(lambda: None)
        result = self.result()
        result.startTest(test)
        result.addSkip(test, 'synthetic missing dependency')
        result.stopTest(test)
        report = outcome([test.id(), 'not.started'], result)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['passed'], 0)
        self.assertEqual(report['skipped'], 1)
        self.assertEqual(report['not_started'], 1)

    def test_empty_and_expected_failure_suites_do_not_pass(self):
        result = self.result()
        self.assertEqual(outcome([], result)['status'], 'failed')
        result.expectedFailures.append((SimpleNamespace(id=lambda: 'expected.failure'), 'synthetic'))
        self.assertEqual(outcome(['expected.failure'], result)['status'], 'failed')

    def test_started_without_success_is_not_a_pass(self):
        test = unittest.FunctionTestCase(lambda: None)
        result = self.result()
        result.startTest(test)
        self.assertEqual(outcome([test.id()], result)['status'], 'failed')
        self.assertEqual(outcome([test.id()], result)['passed'], 0)

    def test_provider_and_unapproved_database_connections_are_refused(self):
        import psycopg
        import socket
        name = 'test_dic_core_20261106000000_1234abcd'
        parameters = dict(host='127.0.0.1', port='5432', user='dawana_ci',
            password='ci-ephemeral-only', dbname=name, sslmode='disable')
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'DAWANA_CI_ACCEPTANCE': '1'}), \
                patch('psycopg.connect') as real_connect:
            with guarded_connections(name, 5432):
                psycopg.connect(**parameters)
                real_connect.assert_called_once()
                real_connect.reset_mock()
                for changes in ({'dbname': 'dawana_dev'}, {'dbname': 'dic_2026_demo'},
                        {'dbname': 'unapproved_production'}, {'dbname': 'unapproved_database'}, {'host': 'external.example.test'},
                        {'port': '5433'}, {'user': 'other'}, {'sslmode': 'require'}):
                    with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                        psycopg.connect(**{**parameters, **changes})
                with self.assertRaises(RuntimeError): socket.create_connection(('external.example.test', 443))
                real_connect.assert_not_called()

    def test_guard_cannot_be_initialized_with_protected_database_names(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'DAWANA_CI_ACCEPTANCE': '1'}):
            for name in ('dawana_dev', 'dic_2026_demo', 'unapproved_production', 'postgres'):
                with self.subTest(name=name), self.assertRaises(RuntimeError):
                    guarded_connections(name, 5432)
