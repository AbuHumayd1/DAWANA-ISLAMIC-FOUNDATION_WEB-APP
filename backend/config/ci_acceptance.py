"""CI-only discovery, connection guards, migration evidence and honest counts."""
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
import ast
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from django.test.runner import DiscoverRunner

APPS = ('accounts', 'config', 'health', 'dic', 'dic_scoring', 'dic_finance', 'dic_movement', 'dic_assistance')
REGRESSION_PREFIX = 'dic.test_production_payments.PaymentEntitlementModeTests.'


def require_ci():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('DAWANA_CI_ACCEPTANCE') != '1':
        raise RuntimeError('This runner is only for the disposable GitHub Actions job.')


def partition_for(test_id):
    if test_id.startswith(('dic.test_registration_privacy.', 'dic.test_tutor_registration.')):
        return 'tutor'
    if test_id.startswith('dic_movement.test_integration.'):
        return 'movement'
    if test_id.startswith('dic_assistance.test_integration.'):
        return 'assistance'
    return 'core'


def flatten(suite):
    for node in suite:
        if isinstance(node, unittest.TestSuite):
            yield from flatten(node)
        else:
            yield node


def regression_ids():
    source = Path(__file__).resolve().parents[1] / 'dic/test_production_payments.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'PaymentEntitlementModeTests']
    if len(classes) != 1:
        raise RuntimeError('Payment-mode regression class is missing or ambiguous.')
    return {REGRESSION_PREFIX + node.name for node in classes[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')}


def validate_regressions(test_ids):
    expected = regression_ids()
    actual = {name for name in test_ids if name.startswith(REGRESSION_PREFIX)}
    if len(expected) != 9 or actual != expected:
        raise RuntimeError('All nine payment-mode regressions must be discovered.')


def guarded_connections(database_name, port):
    """Python outbound sockets are forbidden; libpq has its own exact guard."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from django.db.backends.base.base import BaseDatabaseWrapper
    require_ci()
    if (not re.fullmatch(r'test_dic_(?:core|tutor|movement|assistance)_[0-9]{14}_[a-f0-9]{8}', database_name)
            or not str(port).isdigit() or not 1 <= int(port) <= 65535):
        raise RuntimeError('Invalid disposable CI database identity.')
    original_connect = psycopg.connect
    original_ensure = BaseDatabaseWrapper.ensure_connection

    def deny(*args, **kwargs):
        raise RuntimeError('Outbound networking is forbidden during backend acceptance.')

    def connect(conninfo='', **kwargs):
        parameters = conninfo_to_dict(conninfo, **{key: value for key, value in kwargs.items()
            if key not in ('autocommit', 'prepare_threshold', 'context', 'row_factory', 'cursor_factory')})
        if (parameters.get('host') != '127.0.0.1' or parameters.get('hostaddr') not in (None, '127.0.0.1')
                or str(parameters.get('port')) != str(port)
                or parameters.get('user') != 'dawana_ci' or parameters.get('password') != 'ci-ephemeral-only'
                or parameters.get('dbname') not in ('postgres', database_name)
                or parameters.get('service') or parameters.get('passfile')
                or parameters.get('sslmode') != 'disable'):
            raise RuntimeError('Connection outside the exact ephemeral CI database boundary refused.')
        return original_connect(conninfo, **kwargs)

    def ensure(connection):
        if connection.settings_dict.get('ENGINE') != 'django.db.backends.postgresql':
            raise RuntimeError('Only the guarded CI PostgreSQL backend may connect.')
        return original_ensure(connection)

    stack = ExitStack()
    stack.enter_context(patch('socket.socket.connect', deny))
    stack.enter_context(patch('socket.socket.connect_ex', deny))
    stack.enter_context(patch('socket.create_connection', deny))
    stack.enter_context(patch('psycopg.connect', connect))
    stack.enter_context(patch.object(BaseDatabaseWrapper, 'ensure_connection', ensure))
    return stack


class CountedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_ids = []
        self.passed_ids = []

    def startTest(self, test):
        self.started_ids.append(test.id())
        super().startTest(test)

    def addSuccess(self, test):
        self.passed_ids.append(test.id())
        super().addSuccess(test)


def outcome(test_ids, result):
    missing = list((Counter(test_ids) - Counter(result.started_ids)).elements())
    failed = bool(result.failures or result.errors or result.skipped or result.expectedFailures
        or result.unexpectedSuccesses or missing or not test_ids
        or Counter(result.passed_ids) != Counter(test_ids))
    return {
        'status': 'failed' if failed else 'passed', 'discovered': len(test_ids),
        'started': result.testsRun, 'passed': len(result.passed_ids),
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'expected_failures': len(result.expectedFailures), 'unexpected_successes': len(result.unexpectedSuccesses),
        'not_started': len(missing), 'not_started_ids': missing,
        'discovered_ids': test_ids, 'started_ids': result.started_ids,
        'failed_ids': [test.id() for test, _ in result.failures],
        'error_ids': [test.id() for test, _ in result.errors],
        'skipped_tests': [{'id': test.id(), 'reason': reason} for test, reason in result.skipped],
    }


def write_report(name, report):
    require_ci()
    root = Path(os.environ['RUNNER_TEMP']).resolve()
    target = root / 'dawana-backend-results'
    target.mkdir(exist_ok=True)
    # Preserve earlier evidence and refuse a stale rerun instead of overwriting it.
    with (target / (name + '.json')).open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
    print(json.dumps({key: value for key, value in report.items()
        if not key.endswith('_ids') and key != 'skipped_tests'}, sort_keys=True))


def run_policy_suite(suite):
    require_ci()
    if (Path(os.environ['RUNNER_TEMP']) / 'dawana-backend-results/policy.json').exists():
        raise RuntimeError('Existing policy evidence must not be reused or overwritten.')
    ids = [test.id() for test in flatten(suite)]
    validate_regressions(ids)
    result = unittest.TextTestRunner(verbosity=2, resultclass=CountedResult).run(suite)
    report = outcome(ids, result)
    write_report('policy', report)
    return report['status'] == 'passed'


class IsolatedCacheResult(CountedResult):
    """Keep real throttles within each test, without cross-test cache history."""

    def startTest(self, test):
        from django.core.cache import caches
        for cache in caches.all():
            cache.clear()
        super().startTest(test)

    def stopTest(self, test):
        from django.core.cache import caches
        try:
            for cache in caches.all():
                cache.clear()
        finally:
            super().stopTest(test)


class AcceptanceRunner(DiscoverRunner):
    test_runner = unittest.TextTestRunner

    def __init__(self, partition, **kwargs):
        require_ci()
        self.partition = partition
        self.evidence = {'status': 'not_executed', 'partition': partition}
        super().__init__(verbosity=2, interactive=False, keepdb=False, parallel=1, **kwargs)

    def build_suite(self, *args, **kwargs):
        suite = super().build_suite(APPS, **kwargs)
        discovered = list(flatten(suite))
        all_ids = [test.id() for test in discovered]
        validate_regressions(all_ids)
        if any(type(test).__name__ == '_FailedTest' for test in discovered):
            raise RuntimeError('Backend test discovery contains an import error; no partition may hide it.')
        selected = [test for test in discovered if partition_for(test.id()) == self.partition]
        self.selected_ids = [test.id() for test in selected]
        if not selected:
            raise RuntimeError('Empty CI partition refused.')
        self.evidence.update(discovered=len(selected), all_discovered_ids=all_ids,
                             discovered_ids=self.selected_ids)
        return unittest.TestSuite(selected)

    def get_test_runner_kwargs(self):
        return {**super().get_test_runner_kwargs(), 'resultclass': IsolatedCacheResult}

    def setup_databases(self, **kwargs):
        old = super().setup_databases(**kwargs)  # Unchanged, complete migration graph.
        from django.core.management import call_command
        from django.db import connection
        from dic.models import CampEdition
        if connection.settings_dict['NAME'] != os.environ['DAWANA_CI_DATABASE']:
            raise RuntimeError('CI migration target mismatch.')
        edition = CampEdition.objects.get(year=2026)
        expected = {
            'pre_primary': (Decimal('4000'), Decimal('5000')),
            'primary': (Decimal('10000'), Decimal('12000')),
            'secondary': (Decimal('12000'), Decimal('15000')),
            'undergraduate': (Decimal('15000'), Decimal('17000')),
            'graduate_adult': (Decimal('18000'), Decimal('18500')),
        }
        actual = {row.payment_kind: (row.early_bird_fee_ngn, row.fee_ngn)
                  for row in edition.registration_categories.all()}
        if (actual != expected or edition.is_active or edition.registration_status != 'draft'
                or edition.registration_open_date is not None or edition.registration_close_date is not None
                or edition.early_bird_cutoff_at is not None or edition.name != 'Darul Islam Camp 2026'
                or edition.venue_name != 'Fazil Umar Secondary School, Lagos'
                or edition.general_information.get('theme') != 'The Outliers'
                or edition.camp_start_date != date(2026, 12, 23) or edition.camp_end_date != date(2027, 1, 1)):
            raise RuntimeError('Fresh migration reference data does not match the approved release.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT tgname FROM pg_trigger WHERE NOT tgisinternal')
            triggers = {row[0] for row in cursor.fetchall()}
            cursor.execute("SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace")
            functions = {row[0] for row in cursor.fetchall()}
            constraints = connection.introspection.get_constraints(cursor, 'dic_paymentattempt')
        if not {'dic_enrollment_source_guard', 'dic_enrolled_item_guard',
                'dic_enrolled_order_guard', 'dic_registered_category_guard'} <= triggers:
            raise RuntimeError('Required PostgreSQL integrity triggers are missing.')
        if not {'dic_check_enrollment_source', 'dic_protect_enrolled_item',
                'dic_protect_enrolled_order', 'dic_protect_registered_category'} <= functions:
            raise RuntimeError('Required PostgreSQL integrity functions are missing.')
        if ('dic_one_unresolved_payment_per_order' not in constraints
                or not constraints['dic_one_unresolved_payment_per_order']['unique']
                or not any(row['unique'] and row['columns'] == ['provider_transaction_id']
                           for row in constraints.values())):
            raise RuntimeError('Required payment uniqueness constraints/indexes are missing.')
        self.evidence['fresh_migrations_and_reference_data'] = 'passed'
        # Existing TestCase fixtures expect empty application tables. Verify the
        # migrated seed FIRST, then flush ONLY this exact disposable CI database.
        # This retains schema, migration history, triggers and recreated permissions.
        call_command('flush', interactive=False, verbosity=0, database='default')
        return old

    def suite_result(self, suite, result, **kwargs):
        self.evidence.update(outcome(self.selected_ids, result))
        return int(self.evidence['status'] != 'passed')

    def run_tests(self, *args, **kwargs):
        try:
            return super().run_tests(*args, **kwargs)
        except BaseException as error:
            self.evidence.update(status='setup_or_runner_failed', exception_type=type(error).__name__)
            raise
        finally:
            write_report(self.partition, self.evidence)
