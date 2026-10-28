"""Single-use local assistance test provisioning. No drop, flush or operational DB actions."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TARGET = ('dic_assistance', '0001_initial')
PATTERN = r'test_dic_assistance_[0-9]{14}_[a-f0-9]{8}'


def graph():
    from django.apps import apps
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    from django.core.management import call_command
    loader = MigrationLoader(None)
    nodes = loader.graph.forwards_plan(TARGET)
    allowed = lambda app, name: (
        app == 'dic' and name[:4].isdigit() and 1 <= int(name[:4]) <= 26
        or (app, name) == TARGET
        or (app, name) == ('accounts', '0001_initial')
        or app == 'auth' and name[:4].isdigit() and 1 <= int(name[:4]) <= 12
        or app == 'contenttypes' and name in ('0001_initial', '0002_remove_content_type_name'))
    if not all(allowed(*node) for node in nodes):
        raise RuntimeError('Unexpected migration prerequisite; stop for review.')
    if set(loader.get_migration(*TARGET).dependencies) != {('dic', '0026_house_score_transaction'), ('accounts', '__first__')}:
        raise RuntimeError('Unexpected direct assistance dependencies.')
    if ('dic', '0026_house_score_transaction') not in nodes:
        raise RuntimeError('Missing approved prerequisite.')
    changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
    if changes.get('dic_assistance'): raise RuntimeError('Assistance model drift.')
    call_command('check', verbosity=1)
    digest = hashlib.sha256()
    for node in nodes:
        module = sys.modules[loader.get_migration(*node).__class__.__module__]
        digest.update('.'.join(node).encode())
        digest.update(Path(module.__file__).read_bytes())
    print('Exact disposable migration plan (0027 excluded):', nodes)
    return nodes, digest.hexdigest()


def verify(helper, name, nodes):
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    helper.verify_connection_identity(name, connection)
    if set(MigrationLoader(connection).applied_migrations) != set(nodes):
        raise RuntimeError('Applied migration set differs from approved target prerequisites.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.dic_welfarereport'), to_regclass('public.dic_anonymouscamperresponse'), to_regclass('public.dic_assistance_registrationassistance')")
        row = cursor.fetchone()
        if row[:2] != (None, None) or row[2] is None:
            raise RuntimeError('Missing assistance schema or postponed tables present.')
    from dic.models import RegistrationOrder, PaymentAttempt, RegistrationRecoveryChallenge
    from dic_assistance.models import RegistrationAssistance
    print('Read-only verification counts:', {
        'orders': RegistrationOrder.objects.count(), 'assistance': RegistrationAssistance.objects.count(),
        'payments': PaymentAttempt.objects.count(), 'recovery_challenges': RegistrationRecoveryChallenge.objects.count()})
    print('PASS: exact schema history; no 0027. Synthetic concurrency fixtures may remain after tests.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'schema', 'verify'])
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    if args.action == 'create':
        name = 'test_dic_assistance_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:8]
        # Reserve the receipt before any DB action; partial failures are retained,
        # never silently reused or automatically deleted.
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open('x', encoding='utf-8') as handle:
            json.dump({'database': name, 'status': 'reserved'}, handle)
    else:
        name = json.loads(args.receipt.read_text(encoding='utf-8'))['database']
    if not re.fullmatch(PATTERN, name): raise RuntimeError('Refusing protected/non-disposable database name.')
    spec = importlib.util.spec_from_file_location('assistance_provision_helpers', ROOT / 'scripts' / 'validate_dic_finance.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    credentials = helper.configure(name, readonly=args.action == 'verify')
    from django.conf import settings
    settings.DIC_ASSISTED_BOOKING_ENABLED = False
    with ExitStack() as stack:
        helper.guards(stack, credentials)
        nodes, digest = graph()
        if args.action == 'create':
            from psycopg import sql
            marker = 'dawana-assistance-validation:' + uuid.uuid4().hex
            with helper.admin_connect(credentials) as conn:
                identity = conn.execute('SELECT current_database(), host(inet_server_addr()), inet_server_port()').fetchone()
                if identity != ('postgres', credentials['host'], credentials['port']):
                    raise RuntimeError('Unexpected maintenance server identity.')
                if not conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]:
                    raise RuntimeError('Local role lacks CREATEDB; no grants will be changed.')
                if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', [name]).fetchone():
                    raise RuntimeError('Database already exists; refuse reuse.')
                conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
                conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name), sql.Literal(marker)))
                oid, owner, actual_marker = conn.execute("SELECT oid,pg_get_userbyid(datdba),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", [name]).fetchone()
                if actual_marker != marker or owner != credentials['user']:
                    raise RuntimeError('Created database owner/marker mismatch.')
            receipt = dict(database=name, host=credentials['host'], port=credentials['port'], user=credentials['user'],
                oid=oid, owner=owner, marker=marker, migration_digest=digest, status='created')
            args.receipt.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            helper.receipt_load(args.receipt, name, credentials)
            print('Created and verified fresh marked database:', name)
            return
        receipt = helper.receipt_load(args.receipt, name, credentials)
        if receipt['migration_digest'] != digest: raise RuntimeError('Migration files changed since creation; refuse.')
        from django.db import connection, connections
        if args.action == 'schema':
            helper.verify_connection_identity(name, connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                if cursor.fetchone()[0] != 0: raise RuntimeError('Schema action is single-use: expected empty public schema.')
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan([TARGET])
            if executor.loader.applied_migrations or [(m.app_label, m.name) for m, backwards in plan] != nodes or any(backwards for _, backwards in plan):
                raise RuntimeError('Unexpected initial migration plan.')
            print('Applying only reviewed prerequisites and assistance target to', name)
            executor.migrate([TARGET], plan=plan)
            # No management migrate/post_migrate: no permission seed or grants.
        verify(helper, name, nodes)
        connections.close_all()


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        print('Retain partial receipt/database for diagnosis; no automatic cleanup or reuse.', file=sys.stderr)
        sys.exit(1)
