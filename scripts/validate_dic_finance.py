"""Prepared procedure: explicit Finance tests and targeted disposable schema only.

Nothing runs on import. This helper has no protected-database write action.
"""
import argparse
from contextlib import ExitStack
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
import urllib.request
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TARGET = ('dic_finance', '0001_initial')
FORBIDDEN = ('dic', '0027_feedback_welfare')
PROTECTED = {'dawana_dev', 'test_dic_portal_2026_local'}
NAME_PATTERN = r'test_dic_finance_[0-9]{14}_[a-f0-9]{8}'
POLICY = (
    'test_money_exact_minor_units',
    'test_money_rejects_nonfinite_negative_fractional_and_oversized',
    'test_finance_requires_active_staff_operations_and_finance',
    'test_action_permission_is_independent',
    'test_verified_receipt_uses_trusted_payment_evidence',
    'test_pending_failed_duplicate_and_mismatch_are_not_income',
    'test_refunded_and_cancelled_orders_are_excluded',
    'test_missing_provider_id_or_amount_mismatch_is_exception',
    'test_invalid_payment_timing_is_excluded',
    'test_formula_injection_is_escaped_by_shared_export_utility',
    'test_duplicate_order_and_provider_credit_count_once',
    'test_documented_reversal_never_credits_revenue',
    'test_creator_cannot_approve_own_expense',
    'test_approval_does_not_mark_expense_paid_and_is_audited',
    'test_stale_workflow_version_is_rejected',
    'test_api_rejects_anonymous_before_finance_storage',
    'test_budgets_and_approved_commitments_are_not_cash_expenses',
    'test_only_verified_income_and_paid_expense_count',
    'test_pending_failed_attempts_are_counts_not_revenue',
)
INTEGRATION = (
    'test_expense_approval_payment_reversal_and_audit',
    'test_budget_revision_replaces_allocation_without_cash_effect',
    'test_cross_edition_category_cannot_be_used',
    'test_stale_version_and_unauthorised_action_do_not_write',
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def configure(name, readonly=False):
    sys.path.insert(0, str(ROOT / 'backend'))
    import environ
    environ.Env.read_env(ROOT / 'backend' / '.env')
    env = environ.Env()
    source = env.db_url('DATABASE_URL') if env('DATABASE_URL', default='') else dict(
        ENGINE='django.db.backends.postgresql', HOST=env('DB_HOST', default='127.0.0.1'),
        PORT=env('DB_PORT', default='5432'), USER=env('DB_USER'), PASSWORD=env('DB_PASSWORD', default=''))
    require(source['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL is required.')
    require(source.get('HOST') in ('localhost', '127.0.0.1', '::1'), 'Refusing non-loopback PostgreSQL.')
    require(os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.development') == 'config.settings.development',
            'Refusing a non-development settings module.')
    host = '127.0.0.1' if source['HOST'] == 'localhost' else source['HOST']
    credentials = dict(host=host, hostaddr=host, port=int(source.get('PORT') or 5432),
                       user=source['USER'], password=source.get('PASSWORD') or '', connect_timeout=5)
    # base.py requires every TEST.NAME to start with test_, even when no test
    # database is used. Preserve existing disposable names; prefix development.
    unused_test_name = (name if name.startswith('test_') else 'test_' + name) + '_unused'
    os.environ.update(DATABASE_URL='', DB_NAME=name, DB_HOST=host, DB_PORT=str(credentials['port']),
        DB_USER=credentials['user'], DB_PASSWORD=credentials['password'], DB_TEST_NAME=unused_test_name,
        DJANGO_SETTINGS_MODULE='config.settings.development', DJANGO_DEBUG='True',
        DJANGO_SECRET_KEY='synthetic-finance-validation-' + uuid.uuid4().hex * 2,
        DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,testserver', PAYSTACK_MODE='test',
        PAYSTACK_SECRET_KEY='sk_test_finance_no_network', PAYSTACK_CALLBACK_URL='',
        DIC_EMAIL_RECOVERY_ENABLED='False', DIC_RECOVERY_DELIVERY_WORKER_ENABLED='False',
        DIC_SMS_RECOVERY_ADAPTER='', DIC_WHATSAPP_ACCESS_TOKEN='', DIC_WHATSAPP_PHONE_NUMBER_ID='',
        DIC_RECOVERY_ENCRYPTION_KEY='', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST='', EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='', DEFAULT_FROM_EMAIL='finance@example.test',
        DIC_MEMORY_STORAGE='disabled', DIC_MEMORY_S3_BUCKET='', DIC_MEMORY_S3_ENDPOINT='',
        DIC_OFFICIAL_LOGO_URL='', AWS_EC2_METADATA_DISABLED='true',
        AWS_ACCESS_KEY_ID='synthetic-no-network', AWS_SECRET_ACCESS_KEY='synthetic-no-network', AWS_SESSION_TOKEN='')
    import django
    django.setup()
    from django.conf import settings
    require(settings.DEBUG and settings.SETTINGS_MODULE == 'config.settings.development', 'Development settings required.')
    require(set(settings.DATABASES) == {'default'}, 'Unexpected database aliases; stop.')
    require(settings.DATABASES['default']['NAME'] == name, 'Unexpected database selection.')
    settings.DATABASES['default']['OPTIONS'] = dict(connect_timeout=5, hostaddr=host,
        options='-c statement_timeout=30000 -c default_transaction_read_only=' + ('on' if readonly else 'off'))
    return credentials


def graph_checks():
    from django.apps import apps
    from django.core.management import call_command
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    loader = MigrationLoader(None)
    nodes = loader.graph.forwards_plan(TARGET)
    require(FORBIDDEN not in nodes, 'Unexpected postponed migration dependency.')
    require(('dic', '0026_house_score_transaction') in nodes, 'Missing approved DIC dependency.')
    for app, migration in nodes:
        allowed = (app == 'dic' and migration[:4].isdigit() and 1 <= int(migration[:4]) <= 26
            or app == 'dic_finance' and migration == TARGET[1]
            or app == 'accounts' and migration == '0001_initial'
            or app == 'auth' and migration[:4].isdigit() and 1 <= int(migration[:4]) <= 12
            or app == 'contenttypes' and migration in ['0001_initial', '0002_remove_content_type_name'])
        require(allowed, f'Unexpected dependency: {app}.{migration}')
    require(set(loader.get_migration(*TARGET).dependencies) == {
        ('dic', '0026_house_score_transaction'), ('accounts', '__first__')}, 'Unexpected direct Finance dependencies.')
    changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
    require(not changes.get('dic_finance'), 'Finance model/migration drift; stop and review.')
    call_command('check', verbosity=1)
    fingerprint = hashlib.sha256()
    for node in nodes:
        module = sys.modules[loader.get_migration(*node).__class__.__module__]
        fingerprint.update('.'.join(node).encode())
        fingerprint.update(Path(module.__file__).read_bytes())
    print('Approved dependency plan (not applied):')
    for node in nodes:
        print('  ' + '.'.join(node))
    return nodes, fingerprint.hexdigest()


def denied(*args, **kwargs):
    raise RuntimeError('External side effects or database setup are disabled in this validation phase.')


def guards(stack, credentials, no_database=False):
    def connect(sock, address):
        if no_database or not isinstance(address, tuple) or address[0] not in ('localhost','127.0.0.1','::1') or address[1] != credentials['port']:
            denied()
        return original_connect(sock, address)
    original_connect = socket.socket.connect
    stack.enter_context(patch.object(socket.socket, 'connect', connect))
    stack.enter_context(patch.object(socket.socket, 'connect_ex', denied))
    stack.enter_context(patch.object(http.client.HTTPConnection, 'connect', denied))
    stack.enter_context(patch.object(http.client.HTTPSConnection, 'connect', denied))
    stack.enter_context(patch.object(urllib.request, 'urlopen', denied))
    stack.enter_context(patch.object(subprocess, 'Popen', denied))
    stack.enter_context(patch('dic.payments.urlopen', denied))
    if no_database:
        from django.db.backends.base.base import BaseDatabaseWrapper
        stack.enter_context(patch.object(BaseDatabaseWrapper, 'ensure_connection', denied))


def tests(which):
    from django.test import SimpleTestCase, TestCase
    from django.test.runner import iter_test_cases
    from django.test.utils import setup_test_environment, teardown_test_environment
    from django.db import connections
    names = POLICY if which == 'policy' else INTEGRATION
    label = 'dic_finance.tests.FinancePolicyTests' if which == 'policy' else 'dic_finance.test_integration.FinanceIntegrationTests'
    module = __import__(label.rsplit('.',1)[0], fromlist=[label.rsplit('.',1)[1]])
    cls = getattr(module, label.rsplit('.',1)[1])
    require(set(unittest.defaultTestLoader.getTestCaseNames(cls)) == set(names), 'Test manifest changed; review the allowlist.')
    suite = unittest.defaultTestLoader.loadTestsFromNames([label + '.' + name for name in names])
    cases = list(iter_test_cases(suite))
    require(len(cases) == len(names), 'Unexpected test count/import error.')
    if which == 'policy':
        require(all(isinstance(t, SimpleTestCase) and not t.databases for t in cases), 'Policy suite must be database-free.')
    else:
        require(all(isinstance(t, TestCase) and t.databases == {'default'} for t in cases), 'Only transaction-wrapped Finance TestCase tests are permitted.')
        require(not cls.fixtures and cls.available_apps is None and not cls.reset_sequences and not cls.serialized_rollback,
                'Unexpected fixture/flush/serialization configuration; stop.')
        require(connections['default'].features.supports_transactions and connections['default'].features.uses_savepoints,
                'PostgreSQL transactions/savepoints are required; no flush fallback is allowed.')
    # No DiscoverRunner, setup_databases(), create_test_db(), post_migrate or flush.
    from django.core.management import call_command
    def safe_command(name, *args, **kwargs):
        if name in ['migrate','flush','loaddata','sqlflush']: denied()
        return call_command(name, *args, **kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch('django.core.management.call_command', safe_command))
        stack.enter_context(patch('django.test.testcases.call_command', safe_command))
        stack.enter_context(patch.object(connections['default'].creation, 'create_test_db', denied))
        stack.enter_context(patch.object(connections['default'].creation, 'destroy_test_db', denied))
        setup_test_environment()
        try:
            result = unittest.TextTestRunner(verbosity=2, failfast=True).run(suite)
        finally:
            teardown_test_environment()
            connections.close_all()
    require(result.wasSuccessful() and result.testsRun == len(names) and not result.skipped,
            'Test failure, incomplete run or skip: stop; retain disposable DB for diagnosis.')
    print(f'PASS: {result.testsRun} {which} tests; 0 failures/errors/skips.')


def admin_connect(credentials, readonly=False):
    import psycopg
    return psycopg.connect(**credentials, dbname='postgres', autocommit=True,
        options='-c statement_timeout=10000 -c default_transaction_read_only=' + ('on' if readonly else 'off'))


def receipt_load(path, name, credentials):
    require(path and path.is_file(), 'Creation receipt is required; refusing unowned database.')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    require(receipt['database'] == name and receipt['host'] == credentials['host']
        and receipt['port'] == credentials['port'] and receipt['user'] == credentials['user'], 'Receipt identity mismatch.')
    with admin_connect(credentials, readonly=True) as conn:
        row = conn.execute("SELECT oid, pg_get_userbyid(datdba), shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", [name]).fetchone()
        require(row and row[0] == receipt['oid'] and row[1] == receipt['owner'] and row[2] == receipt['marker'],
                'Database owner/OID/marker changed; stop.')
    return receipt


def verify_connection_identity(name, connection):
    with connection.cursor() as cursor:
        # Casting inet to text includes /32 or /128. host() returns the address
        # without changing which database/server/port values are permitted.
        cursor.execute('SELECT current_database(), host(inet_server_addr()), inet_server_port()')
        identity = cursor.fetchone()
        expected_port = int(connection.settings_dict['PORT'])
        require(identity[0] == name, f'Unexpected database: expected {name!r}, observed {identity[0]!r}.')
        require(identity[1] in ['127.0.0.1','::1'], f'Unexpected server address: expected loopback, observed {identity[1]!r}.')
        require(identity[2] == expected_port, f'Unexpected server port: expected {expected_port!r}, observed {identity[2]!r}.')
        print('Verified database/server:', identity)


def verify_database(name, nodes):
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    verify_connection_identity(name, connection)
    loader = MigrationLoader(connection)
    applied = set(loader.applied_migrations)
    require(FORBIDDEN not in applied and applied == set(nodes), 'Unexpected applied migration set.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.dic_anonymouscamperresponse'), to_regclass('public.dic_welfarereport')")
        require(cursor.fetchone() == (None,None), 'Postponed schema unexpectedly exists.')
    print('Verified: exact targeted migration set; no dic 0027 or feedback/welfare tables.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight','policy','create','integration','verify','cleanup','development-plan'])
    parser.add_argument('--database', required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    name = args.database
    if args.action == 'development-plan':
        require(name == 'dawana_dev', 'Development planning is restricted to dawana_dev, read-only.')
    else:
        require(name not in PROTECTED and re.fullmatch(NAME_PATTERN,name), 'Unexpected disposable database name; refusing action.')
    credentials = configure(name, readonly=args.action == 'development-plan')
    with ExitStack() as stack:
        guards(stack, credentials, no_database=args.action in ['preflight','policy'])
        if args.action == 'cleanup':
            from django.db import connections
            from psycopg import sql
            receipt_load(args.receipt,name,credentials)
            connections.close_all()
            with admin_connect(credentials) as conn:
                active = conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=%s',[name]).fetchone()[0]
                require(active == 0, 'Disposable database has active connections; close them explicitly. No forced termination.')
                conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
            print('Dropped only the marked disposable database. Receipt retained for audit.')
            return
        nodes, digest = graph_checks()
        if args.action == 'preflight': return
        if args.action == 'policy':
            tests('policy'); return
        if args.action == 'development-plan':
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_setting('transaction_read_only')")
                require(cursor.fetchone() == ('dawana_dev','on'), 'Expected read-only development connection.')
            executor = MigrationExecutor(connection)
            require(FORBIDDEN not in executor.loader.applied_migrations, '0027 already applied; unexpected development state.')
            executor.loader.check_consistent_history(connection)
            plan = executor.migration_plan([TARGET])
            require([(m.app_label,m.name,backwards) for m,backwards in plan] == [('dic_finance','0001_initial',False)],
                    'Expected exactly one pending Finance migration; stop and review actual state.')
            print('DEVELOPMENT PLAN ONLY: dic_finance.0001_initial (four new Finance tables). No migration executed.')
            connection.close(); return
        require(args.receipt is not None, '--receipt is required.')
        if args.action == 'create':
            from psycopg import sql
            require(not args.receipt.exists(), 'Receipt already exists; refuse reuse.')
            args.receipt.parent.mkdir(parents=True,exist_ok=True)
            marker = 'dawana-finance-validation:' + uuid.uuid4().hex
            with admin_connect(credentials) as conn:
                allowed = conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]
                require(allowed, 'Configured local role lacks CREATEDB; stop and request an approved test facility. No grants changed.')
                require(not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',[name]).fetchone(), 'Database exists; refuse reuse.')
                conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
                conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name),sql.Literal(marker)))
                oid, owner = conn.execute('SELECT oid,pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s',[name]).fetchone()
            receipt = dict(database=name,host=credentials['host'],port=credentials['port'],user=credentials['user'],
                           oid=oid,owner=owner,marker=marker,migration_digest=digest)
            with args.receipt.open('x',encoding='utf-8') as handle: json.dump(receipt,handle,indent=2)
            print('Created empty marked disposable database:', name)
            return
        receipt = receipt_load(args.receipt,name,credentials)
        require(receipt['migration_digest'] == digest, 'Migration files changed since creation; stop.')
        from django.db import connection
        if args.action == 'integration':
            from django.db.migrations.executor import MigrationExecutor
            verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                require(cursor.fetchone()[0] == name, 'Wrong database; refusing migration.')
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                require(cursor.fetchone()[0] == 0, 'Expected fresh empty disposable database; refuse rerun/reuse.')
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan([TARGET])
            require(not executor.loader.applied_migrations, 'Unexpected pre-existing migration history.')
            require([ (m.app_label,m.name) for m,backwards in plan ] == nodes and not any(b for _,b in plan),
                    'Unexpected migration plan/order; stop.')
            print('Applying only the displayed prerequisites and Finance target to:',name)
            executor.migrate([TARGET],plan=plan)
            verify_database(name,nodes)
            tests('integration')
            verify_database(name,nodes)
            print('No unrestricted migration sequence, post_migrate or test flush was invoked.')
        elif args.action == 'verify':
            verify_database(name,nodes)
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not dump settings, connection DSNs or credentials on operational errors.
        print('STOP:',type(error).__name__,file=sys.stderr)
        if isinstance(error,RuntimeError): print(str(error),file=sys.stderr)
        else: print('Validation could not complete. Review locally; do not share credentials or raw connection dumps.',file=sys.stderr)
        sys.exit(1)
