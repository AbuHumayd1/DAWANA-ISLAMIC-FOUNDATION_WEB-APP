"""Provision only a marked, fresh, loopback disposable movement database. Never development."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TARGET = ('dic_movement', '0001_initial')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'schema', 'verify'])
    parser.add_argument('--database', required=True)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'test_dic_movement_[0-9]{14}_[a-f0-9]{8}', args.database):
        raise RuntimeError('Refusing protected or unexpected database name.')
    spec = importlib.util.spec_from_file_location('movement_provision_isolation', ROOT / 'scripts' / 'validate_dic_finance.py')
    isolation = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolation)
    credentials = isolation.configure(args.database)
    with ExitStack() as stack:
        isolation.guards(stack, credentials)
        from django.apps import apps
        from django.core.management import call_command
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.autodetector import MigrationAutodetector
        from django.db.migrations.state import ProjectState
        loader = MigrationLoader(None)
        nodes = loader.graph.forwards_plan(TARGET)
        if set(loader.get_migration(*TARGET).dependencies) != {('dic', '0026_house_score_transaction'), ('accounts', '__first__')}:
            raise RuntimeError('Unexpected direct movement dependencies.')
        if ('dic', '0026_house_score_transaction') not in nodes or ('dic', '0027_feedback_welfare') in nodes:
            raise RuntimeError('Unsafe movement plan.')
        for app, name in nodes:
            allowed = (app == 'dic' and name[:4].isdigit() and 1 <= int(name[:4]) <= 26
                or (app, name) == TARGET or (app, name) == ('accounts', '0001_initial')
                or app == 'auth' and name[:4].isdigit() and 1 <= int(name[:4]) <= 12
                or app == 'contenttypes' and name in ('0001_initial', '0002_remove_content_type_name'))
            if not allowed: raise RuntimeError('Unexpected prerequisite.')
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
        if changes.get('dic_movement'): raise RuntimeError('Movement model/migration drift.')
        # No application DB connections permitted by system/model checks.
        with ExitStack() as no_database:
            isolation.guards(no_database, credentials, no_database=True)
            call_command('check', verbosity=1)
        digest = hashlib.sha256()
        for node in nodes:
            module = sys.modules[loader.get_migration(*node).__class__.__module__]
            digest.update('.'.join(node).encode()); digest.update(Path(module.__file__).read_bytes())
        fingerprint = digest.hexdigest()
        print('Reviewed target dependency set (not blanket migration):', nodes)
        if args.action == 'create':
            from psycopg import sql
            if args.receipt.exists(): raise RuntimeError('Receipt exists; refusing overwrite.')
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            marker = 'dawana-movement-validation:' + uuid.uuid4().hex
            with isolation.admin_connect(credentials) as admin:
                allowed = admin.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]
                if not allowed: raise RuntimeError('Local configured role lacks CREATEDB; no grant changes permitted.')
                if admin.execute('SELECT 1 FROM pg_database WHERE datname=%s', [args.database]).fetchone():
                    raise RuntimeError('Database already exists; refusing reuse.')
                admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(args.database)))
                admin.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(args.database), sql.Literal(marker)))
                oid, owner = admin.execute('SELECT oid,pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s', [args.database]).fetchone()
            with args.receipt.open('x', encoding='utf-8') as handle:
                json.dump(dict(database=args.database, host=credentials['host'], port=credentials['port'],
                    user=credentials['user'], oid=oid, owner=owner, marker=marker, migration_digest=fingerprint), handle, indent=2)
            print('Created empty marked disposable database. No schema or development connection.')
            return
        receipt = isolation.receipt_load(args.receipt, args.database, credentials)
        if receipt['migration_digest'] != fingerprint or not re.fullmatch(r'dawana-movement-validation:[a-f0-9]{32}', receipt['marker']):
            raise RuntimeError('Creation identity/graph changed; retain and investigate.')
        isolation.verify_connection_identity(args.database, connection)
        if args.action == 'schema':
            from django.db.migrations.executor import MigrationExecutor
            if connection.introspection.table_names(): raise RuntimeError('Disposable must be empty; refuse schema rerun/reuse.')
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan([TARGET])
            if executor.loader.applied_migrations or [(m.app_label, m.name) for m, _ in plan] != nodes or any(back for _, back in plan):
                raise RuntimeError('Unexpected schema plan. No migration executed.')
            print('Applying the listed prerequisites and movement 0001 only to:', args.database)
            executor.migrate([TARGET], plan=plan)
        applied = set(MigrationLoader(connection).applied_migrations)
        if applied != set(nodes): raise RuntimeError('Unexpected applied migration set.')
        tables = set(connection.introspection.table_names())
        if 'dic_movement_movement' not in tables or {'dic_welfarereport', 'dic_anonymouscamperresponse'} & tables:
            raise RuntimeError('Unexpected movement/postponed table state.')
        print('PASS: exact target migration set and movement table; no dic 0027. No post_migrate or role grants invoked.')
        connection.close()


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        sys.exit(1)
