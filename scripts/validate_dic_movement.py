"""No provisioning/migrations. Policy and graph are DB-free; integration requires an approved marked disposable schema."""
import argparse
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'policy', 'integration'])
    parser.add_argument('--database')
    parser.add_argument('--marker', help='Independently supplied database-comment marker for approved disposable integration only.')
    args = parser.parse_args()
    name = args.database or 'test_dic_movement_20980101000000_00000000'
    if not re.fullmatch(r'test_dic_movement_[0-9]{14}_[a-f0-9]{8}', name):
        raise RuntimeError('Protected/non-disposable database refused.')
    spec = importlib.util.spec_from_file_location('movement_isolation_helpers', ROOT / 'scripts' / 'validate_dic_finance.py')
    isolation = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolation)
    credentials = isolation.configure(name)
    with ExitStack() as stack:
        isolation.guards(stack, credentials, no_database=args.action != 'integration')
        from django.apps import apps
        from django.db import connection, connections
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.autodetector import MigrationAutodetector
        from django.db.migrations.state import ProjectState
        from django.core.management import call_command
        loader = MigrationLoader(None)
        target = ('dic_movement', '0001_initial')
        print('Complete installed migration graph (file graph, not database applied state):')
        for node in sorted(loader.graph.nodes):
            parents = sorted(parent.key for parent in loader.graph.node_map[node].parents)
            print(node, '<-', parents)
        print('Graph leaves:', loader.graph.leaf_nodes())
        if set(loader.get_migration(*target).dependencies) != {('dic', '0026_house_score_transaction'), ('accounts', '__first__')}:
            raise RuntimeError('Unexpected direct movement migration dependencies.')
        nodes = loader.graph.forwards_plan(target)
        if ('dic', '0027_feedback_welfare') in nodes or ('dic', '0026_house_score_transaction') not in nodes:
            raise RuntimeError('Unsafe dependency graph.')
        for app, migration in nodes:
            allowed = (app == 'dic' and migration[:4].isdigit() and 1 <= int(migration[:4]) <= 26
                or (app, migration) == target or app == 'accounts' and migration == '0001_initial'
                or app == 'auth' and migration[:4].isdigit() and 1 <= int(migration[:4]) <= 12
                or app == 'contenttypes' and migration in ('0001_initial', '0002_remove_content_type_name'))
            if not allowed: raise RuntimeError('Unexpected migration dependency.')
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
        print('Model/migration drift app labels:', sorted(changes))
        if changes.get('dic_movement'): raise RuntimeError('Movement model/migration drift.')
        call_command('check', verbosity=1)
        print('Movement graph/model preflight; no migrations applied:', nodes)
        if args.action == 'preflight': return
        if args.action == 'integration':
            if not args.marker or not re.fullmatch(r'dawana-movement-validation:[a-f0-9]{32}', args.marker):
                raise RuntimeError('Approved disposable database marker is required.')
            isolation.verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_get_userbyid(datdba)=current_user, shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()")
                row = cursor.fetchone()
                if row != (True, args.marker): raise RuntimeError('Disposable ownership/marker mismatch.')
            live_loader = MigrationLoader(connection)
            if set(live_loader.applied_migrations) != set(nodes): raise RuntimeError('Expected exactly the reviewed movement target dependencies, no 0027.')
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.dic_welfarereport'), to_regclass('public.dic_anonymouscamperresponse')")
                if cursor.fetchone() != (None, None): raise RuntimeError('Postponed schema present.')
        label = 'dic_movement.tests.MovementPolicyTests' if args.action == 'policy' else 'dic_movement.test_integration.MovementIntegrationTests'
        from django.test import SimpleTestCase, TestCase
        from django.test.runner import iter_test_cases
        from django.test.utils import setup_test_environment, teardown_test_environment
        suite = unittest.defaultTestLoader.loadTestsFromName(label)
        cases = list(iter_test_cases(suite))
        if not cases or not all(isinstance(case, SimpleTestCase if args.action == 'policy' else TestCase) for case in cases):
            raise RuntimeError('Unexpected test class/import failure.')
        if args.action == 'policy' and any(case.databases for case in cases): raise RuntimeError('Policy tests must be database-free.')
        if args.action == 'integration' and (not connection.features.supports_transactions or not connection.features.uses_savepoints):
            raise RuntimeError('Transactional tests required; no flush fallback permitted.')
        from unittest.mock import patch
        stack.enter_context(patch('django.test.testcases.call_command', isolation.denied))
        stack.enter_context(patch.object(connection.creation, 'create_test_db', isolation.denied))
        stack.enter_context(patch.object(connection.creation, 'destroy_test_db', isolation.denied))
        setup_test_environment()
        try: result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            teardown_test_environment(); connections.close_all()
        if not result.wasSuccessful() or result.skipped or result.testsRun != len(cases):
            raise RuntimeError('Movement test run failed, skipped or incomplete.')
        print(f'PASS: {result.testsRun} {args.action} tests, no skips.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        sys.exit(1)
