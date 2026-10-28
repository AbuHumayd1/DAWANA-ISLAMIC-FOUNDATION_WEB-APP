"""Focused privacy checks; fresh marked PostgreSQL only, read-only development planning."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
TARGET = ('dic', '0028_registration_privacy_measurements')
FORBIDDEN = ('dic', '0027_feedback_welfare')
PATTERN = r'test_dic_privacy_[0-9]{14}_[a-f0-9]{8}'


def graph():
    from django.apps import apps
    from django.core.management import call_command
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    loader = MigrationLoader(None)
    if loader.detect_conflicts(): raise RuntimeError('Migration conflicts; stop.')
    migration = loader.get_migration(*TARGET)
    if migration.dependencies != [('dic', '0026_house_score_transaction')] or migration.run_before != [FORBIDDEN]:
        raise RuntimeError('Unexpected Phase 2 migration edges.')
    nodes = loader.graph.forwards_plan(TARGET)
    if FORBIDDEN in nodes or ('dic', '0026_house_score_transaction') not in nodes:
        raise RuntimeError('Unsafe Phase 2 plan.')
    if TARGET not in loader.graph.forwards_plan(FORBIDDEN): raise RuntimeError('Phase 5 must follow Phase 2.')
    for app, name in nodes:
        allowed = ((app, name) == TARGET or app == 'dic' and name[:4].isdigit() and 1 <= int(name[:4]) <= 26
            or (app, name) == ('accounts', '0001_initial')
            or app == 'auth' and name[:4].isdigit() and 1 <= int(name[:4]) <= 12
            or app == 'contenttypes' and name in ('0001_initial', '0002_remove_content_type_name'))
        if not allowed: raise RuntimeError('Unexpected migration prerequisite.')
    changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
    if changes.get('dic'): raise RuntimeError('Core model/migration drift.')
    call_command('check', verbosity=1)
    digest = hashlib.sha256()
    for node in nodes + [FORBIDDEN]:
        module = sys.modules[loader.get_migration(*node).__class__.__module__]
        digest.update('.'.join(node).encode()); digest.update(Path(module.__file__).read_bytes())
    print('Exact Phase 2 dependency plan:', nodes)
    print('Dic leaf:', loader.graph.leaf_nodes('dic'), '; Phase 5 remains deferred.')
    return nodes, digest.hexdigest()


def verify(helper, name, nodes):
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    helper.verify_connection_identity(name, connection)
    if set(MigrationLoader(connection).applied_migrations) != set(nodes):
        raise RuntimeError('Unexpected disposable migration set.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.dic_welfarereport'), to_regclass('public.dic_anonymouscamperresponse')")
        if cursor.fetchone() != (None, None): raise RuntimeError('Postponed tables present.')
    from dic.models import Participant, RegistrationOrder, PaymentAttempt
    if Participant.objects.exists() or RegistrationOrder.objects.exists() or PaymentAttempt.objects.exists():
        raise RuntimeError('Expected no retained business fixtures; do not reuse a dirty test database.')
    print('PASS: exact privacy schema; no 0027 or retained business records.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'policy', 'development-plan', 'create', 'schema', 'integration', 'verify'])
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.action in ('create', 'schema', 'integration', 'verify') and args.receipt is None:
        raise RuntimeError('A creation receipt is required.')
    if args.action == 'create':
        name = 'test_dic_privacy_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:8]
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open('x', encoding='utf-8') as handle:
            json.dump({'database': name, 'status': 'reserved'}, handle)
    elif args.action in ('schema', 'integration', 'verify'):
        name = json.loads(args.receipt.read_text(encoding='utf-8'))['database']
    else:
        name = 'dawana_dev' if args.action == 'development-plan' else 'test_dic_privacy_20980101000000_00000000'
    if name != 'dawana_dev' and not re.fullmatch(PATTERN, name): raise RuntimeError('Unexpected database name.')
    if name == 'dawana_dev' and args.action != 'development-plan': raise RuntimeError('Operational writes forbidden.')
    spec = importlib.util.spec_from_file_location('privacy_isolation', ROOT / 'scripts' / 'validate_dic_finance.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    credentials = helper.configure(name, readonly=args.action in ('development-plan', 'verify'))
    from django.conf import settings
    settings.DIC_ASSISTED_BOOKING_ENABLED = False
    with ExitStack() as stack:
        helper.guards(stack, credentials, no_database=args.action in ('policy', 'preflight'))
        nodes, digest = graph()
        if args.action == 'preflight': return
        from django.db import connection, connections
        if args.action == 'development-plan':
            from django.db.migrations.executor import MigrationExecutor
            helper.verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('transaction_read_only')")
                if cursor.fetchone() != ('on',): raise RuntimeError('Read-only connection required.')
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            if FORBIDDEN in executor.loader.applied_migrations: raise RuntimeError('0027 unexpectedly applied.')
            plan = [(migration.app_label, migration.name, backwards) for migration, backwards in executor.migration_plan([TARGET])]
            if plan != [('dic', TARGET[1], False)]: raise RuntimeError('Expected exactly the pending Phase 2 node.')
            print('READ-ONLY PLAN VERIFIED:', plan, '; no migration executed.')
            connections.close_all(); return
        if args.action == 'create':
            from psycopg import sql
            marker = 'dawana-privacy-validation:' + uuid.uuid4().hex
            with helper.admin_connect(credentials) as conn:
                identity = conn.execute('SELECT current_database(), host(inet_server_addr()), inet_server_port()').fetchone()
                if identity != ('postgres', credentials['host'], credentials['port']): raise RuntimeError('Unexpected maintenance server.')
                if not conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]:
                    raise RuntimeError('Local role lacks CREATEDB; no grants will be changed.')
                if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', [name]).fetchone(): raise RuntimeError('Database exists; refuse.')
                conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
                conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name), sql.Literal(marker)))
                oid, owner = conn.execute('SELECT oid,pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s', [name]).fetchone()
            receipt = dict(database=name, host=credentials['host'], port=credentials['port'], user=credentials['user'],
                oid=oid, owner=owner, marker=marker, migration_digest=digest)
            args.receipt.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            helper.receipt_load(args.receipt, name, credentials)
            print('Created fresh marked privacy test database:', name); return
        if args.action != 'policy':
            receipt = helper.receipt_load(args.receipt, name, credentials)
            if not re.fullmatch(r'dawana-privacy-validation:[a-f0-9]{32}', receipt['marker']): raise RuntimeError('Unexpected marker.')
            if receipt['migration_digest'] != digest: raise RuntimeError('Migration files changed since creation.')
            if args.action == 'schema':
                from django.db.migrations.executor import MigrationExecutor
                helper.verify_connection_identity(name, connection)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                    if cursor.fetchone()[0] != 0: raise RuntimeError('Single-use schema setup requires empty database.')
                executor = MigrationExecutor(connection)
                plan = executor.migration_plan([TARGET])
                if executor.loader.applied_migrations or [(m.app_label, m.name) for m, backwards in plan] != nodes or any(b for _, b in plan):
                    raise RuntimeError('Unexpected disposable migration plan.')
                executor.migrate([TARGET], plan=plan)
                verify(helper, name, nodes); connections.close_all(); return
            verify(helper, name, nodes)
            if args.action == 'verify': connections.close_all(); return
        from django.test import TestCase, SimpleTestCase
        from django.test.runner import iter_test_cases
        from django.test.utils import setup_test_environment, teardown_test_environment
        policy = args.action == 'policy'
        labels = ['dic.test_registration_privacy.RegistrationPrivacyPolicyTests', 'dic.test_assisted_preparation.AssistedPreparationTests'] if policy else [
            'dic.test_registration_privacy.RegistrationPrivacyIntegrationTests',
            'dic.tests.RegistrationApiTests.test_order_accepts_multiple_participants_and_calculates_total']
        suite = unittest.defaultTestLoader.loadTestsFromNames(labels); cases = list(iter_test_cases(suite))
        expected = 19 if policy else 8
        if len(cases) != expected or not all(isinstance(case, SimpleTestCase if policy else TestCase) for case in cases):
            raise RuntimeError('Unexpected test manifest/import failure.')
        if policy and any(case.databases for case in cases): raise RuntimeError('Policy tests must not access DB.')
        if not policy and not (connection.features.supports_transactions and connection.features.uses_savepoints):
            raise RuntimeError('Transactions/savepoints required; no flush fallback.')
        from unittest.mock import patch
        stack.enter_context(patch('django.test.testcases.call_command', helper.denied))
        stack.enter_context(patch('django.core.management.call_command', helper.denied))
        stack.enter_context(patch.object(connection.creation, 'create_test_db', helper.denied))
        stack.enter_context(patch.object(connection.creation, 'destroy_test_db', helper.denied))
        setup_test_environment()
        try: result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally: teardown_test_environment()
        if not result.wasSuccessful() or result.skipped or result.testsRun != expected: raise RuntimeError('Tests failed, skipped or incomplete.')
        if not policy: verify(helper, name, nodes)
        connections.close_all()
        print(f'PASS: {expected} focused {args.action} tests.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        print('No automatic cleanup: retain any disposable receipt/database for diagnosis.', file=sys.stderr)
        sys.exit(1)
