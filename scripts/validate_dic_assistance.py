"""Assistance checks. No migrations or provisioning actions; integration needs a marked disposable schema."""
import argparse
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ('dic_assistance', '0001_initial')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'policy', 'development-plan', 'integration'])
    parser.add_argument('--database')
    parser.add_argument('--marker')
    args = parser.parse_args()
    name = args.database or 'test_dic_assistance_20980101000000_00000000'
    if args.action == 'development-plan':
        if name != 'dawana_dev': raise RuntimeError('Only read-only dawana_dev planning is allowed.')
    elif not re.fullmatch(r'test_dic_assistance_[0-9]{14}_[a-f0-9]{8}', name):
        raise RuntimeError('Only disposable assistance database names are allowed.')
    spec = importlib.util.spec_from_file_location('assistance_isolation', ROOT / 'scripts' / 'validate_dic_finance.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    credentials = helper.configure(name, readonly=args.action == 'development-plan')
    from django.conf import settings
    settings.DIC_ASSISTED_BOOKING_ENABLED = False
    with ExitStack() as stack:
        helper.guards(stack, credentials, no_database=args.action in ('preflight', 'policy'))
        from django.apps import apps
        from django.db import connection, connections
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.autodetector import MigrationAutodetector
        from django.db.migrations.state import ProjectState
        from django.core.management import call_command
        loader = MigrationLoader(None)
        nodes = loader.graph.forwards_plan(TARGET)
        if ('dic', '0027_feedback_welfare') in nodes or ('dic', '0026_house_score_transaction') not in nodes:
            raise RuntimeError('Unsafe assistance dependency graph.')
        if set(loader.get_migration(*TARGET).dependencies) != {('dic', '0026_house_score_transaction'), ('accounts', '__first__')}:
            raise RuntimeError('Unexpected direct dependency.')
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
        if changes.get('dic_assistance'): raise RuntimeError('Assistance model/migration drift.')
        call_command('check', verbosity=1)
        print('Dependency plan (not applied):', nodes)
        print('Other model drift labels (not modified):', sorted(changes))
        if args.action == 'preflight': return
        if args.action == 'development-plan':
            from django.db.migrations.executor import MigrationExecutor
            helper.verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('transaction_read_only'), to_regclass('public.dic_assistance_registrationassistance')")
                if cursor.fetchone() != ('on', None): raise RuntimeError('Expected read-only database without assistance table.')
            for table, columns in {
                'dic_registrationorder': {'id', 'edition_id', 'primary_registrant_id', 'access_token_digest', 'access_token_expires_at', 'idempotency_key_digest'},
                'dic_campedition': {'id', 'is_active'},
                'dic_participant': {'id', 'full_name', 'date_of_birth'},
            }.items():
                with connection.cursor() as cursor:
                    actual_columns = {item.name for item in connection.introspection.get_table_description(cursor, table)}
                if not columns <= actual_columns: raise RuntimeError('Expected supporting core schema columns missing.')
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            if ('dic', '0027_feedback_welfare') in executor.loader.applied_migrations:
                raise RuntimeError('Postponed migration unexpectedly applied.')
            plan = [(m.app_label, m.name, backward) for m, backward in executor.migration_plan([TARGET])]
            if plan != [('dic_assistance', '0001_initial', False)]: raise RuntimeError('Expected exactly the assistance migration; review actual state.')
            from django.db.migrations.recorder import MigrationRecorder
            if ('dic', '0026_house_score_transaction') not in MigrationRecorder(connection).applied_migrations():
                raise RuntimeError('Expected dic 0026 applied.')
            print('READ-ONLY VERIFIED:', plan, 'one new table; no 0027; nothing applied.')
            connections.close_all(); return
        if args.action == 'integration':
            if not args.marker or not re.fullmatch(r'dawana-assistance-validation:[a-f0-9]{32}', args.marker):
                raise RuntimeError('Independently provided disposable database marker required.')
            helper.verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_get_userbyid(datdba)=current_user, shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()")
                if cursor.fetchone() != (True, args.marker): raise RuntimeError('Disposable ownership/marker mismatch.')
            actual = MigrationLoader(connection)
            if set(actual.applied_migrations) != set(nodes): raise RuntimeError('Expected exactly reviewed assistance dependencies in disposable database.')
            from dic_assistance.models import RegistrationAssistance
            from dic.models import RegistrationOrder
            if RegistrationAssistance.objects.exists() or RegistrationOrder.objects.exists():
                raise RuntimeError('Use a fresh disposable schema; retained concurrency fixtures must not be reused.')
        from django.test import SimpleTestCase
        from django.test.runner import iter_test_cases
        from django.test.utils import setup_test_environment, teardown_test_environment
        labels = ['dic_assistance.tests.AssistancePolicyTests', 'dic.test_assisted_preparation.AssistedPreparationTests'] if args.action == 'policy' else [
            'dic_assistance.test_integration.AssistanceIntegrationTests', 'dic_assistance.test_integration.AssistedRecoveryTests',
            'dic_assistance.test_integration.AssistanceConcurrencyTests']
        suite = unittest.defaultTestLoader.loadTestsFromNames(labels)
        cases = list(iter_test_cases(suite))
        expected = 16 if args.action == 'policy' else 9
        if len(cases) != expected or not all(isinstance(case, SimpleTestCase) for case in cases):
            raise RuntimeError('Unexpected test manifest or import failure.')
        if args.action == 'policy' and any(case.databases for case in cases): raise RuntimeError('Policy tests must not use databases.')
        if args.action == 'integration' and not (connection.features.supports_transactions and connection.features.uses_savepoints):
            raise RuntimeError('Transactions/savepoints required; no flush fallback.')
        from unittest.mock import patch
        def safe_command(command, *values, **options):
            if command not in ('send_dic_recovery_messages',): helper.denied()
            return call_command(command, *values, **options)
        stack.enter_context(patch('django.test.testcases.call_command', helper.denied))
        stack.enter_context(patch('django.core.management.call_command', safe_command))
        stack.enter_context(patch.object(connection.creation, 'create_test_db', helper.denied))
        stack.enter_context(patch.object(connection.creation, 'destroy_test_db', helper.denied))
        setup_test_environment()
        try: result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            teardown_test_environment(); connections.close_all()
        if not result.wasSuccessful() or result.skipped or result.testsRun != expected:
            raise RuntimeError('Tests failed, skipped or incomplete.')
        print(f'PASS: {expected} {args.action} tests. No migrations or database provisioning performed.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        sys.exit(1)
