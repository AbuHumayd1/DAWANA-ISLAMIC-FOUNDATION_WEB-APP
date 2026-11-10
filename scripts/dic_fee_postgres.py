"""Guarded local fee tests. No dotenv, protected DB connections or automatic cleanup."""
import argparse
from datetime import datetime, timezone
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import sys
import uuid

PATTERN = r'test_dic_fees_[0-9]{14}_[a-f0-9]{12}'
PROTECTED_OID = 25041


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save_new(path, data):
    # Exclusive creation prevents silently replacing another run's approval/evidence.
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)


def load(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    require(re.fullmatch(PATTERN, data['database']), 'Invalid disposable database name.')
    require(data['host'] == '127.0.0.1' and 1 <= data['port'] <= 65535, 'Loopback endpoint required.')
    require(re.fullmatch(r'[a-f0-9]{32}', data['marker']), 'Invalid creation marker.')
    require(data['identity']['maintenance_oid'] != PROTECTED_OID, 'Protected maintenance database.')
    return data


def connect(data, password, *, readonly):
    import psycopg
    # Do not inherit a libpq service; explicit parameters pin the approved endpoint.
    require(not os.environ.get('PGSERVICE'), 'Inherited PGSERVICE is not allowed for isolated fee tests.')
    return psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=data['port'],
        dbname='postgres', user=data['user'], password=password,
        connect_timeout=5, autocommit=True, application_name='dic_fee_isolation',
        options='-c default_transaction_read_only=' + ('on' if readonly else 'off'), sslmode='disable')


def loopback_address(value):
    try:
        address = ipaddress.ip_address(value)
    except (ValueError, TypeError):
        return False
    mapped = getattr(address, 'ipv4_mapped', None)
    return (mapped or address).is_loopback


def identity(conn):
    row = conn.execute("""SELECT current_database(), current_user, d.oid::bigint,
        inet_server_addr()::text, inet_server_port(), current_setting('server_version_num'),
        (SELECT system_identifier::text FROM pg_control_system()),
        host(inet_server_addr()), host(inet_client_addr()), inet_client_port()
        FROM pg_database d WHERE d.datname=current_database()""").fetchone()
    require(row and row[0] == 'postgres' and row[2] != PROTECTED_OID,
            'Only the unprotected postgres maintenance database may be used.')
    # inet::text includes the netmask (for example 127.0.0.1/32). host(inet)
    # extracts the actual endpoint. Log only this explicit metadata allowlist.
    print('Connection endpoints:', json.dumps(dict(
        server_inet_text=repr(row[3]), server_address=row[7], server_port=row[4],
        client_address=row[8], client_port=row[9])), flush=True)
    require(loopback_address(row[7]) and loopback_address(row[8]),
            'Server and client TCP endpoints must both be loopback; see metadata above.')
    return dict(user=row[1], maintenance_oid=row[2], address=row[7], port=row[4],
                version=row[5], system_identifier=row[6])


def verify_server(conn, data):
    require(identity(conn) == data['identity'], 'Server/role identity changed since preflight; stop.')


def database_info(conn, name):
    return conn.execute("""SELECT oid::bigint, pg_get_userbyid(datdba),
        shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s""", (name,)).fetchone()


def verify_created(conn, receipt):
    verify_server(conn, receipt)
    row = database_info(conn, receipt['database'])
    require(receipt.get('status') == 'created', 'Completed creation receipt required.')
    require(receipt['oid'] != PROTECTED_OID and receipt['oid'] not in receipt['baseline_oids'],
            'Database OID was present before this run or is protected.')
    require(row == (receipt['oid'], receipt['user'], 'dic-fee-test:' + receipt['marker']),
            'Database OID/owner/marker mismatch; refusing access.')


def run_suite(receipt, password, *, reuse=False):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from unittest.mock import patch
    from contextlib import ExitStack
    raw_connect = psycopg.Connection.connect

    def guarded_connect(conninfo='', **kwargs):
        require(not os.environ.get('PGSERVICE'), 'Inherited PGSERVICE is not allowed for isolated fee tests.')
        # Django also supplies psycopg-only options such as cursor_factory and
        # context; these are not valid libpq conninfo keywords.
        params = conninfo_to_dict(conninfo)
        params.update({key: value for key, value in kwargs.items()
                       if key in ('dbname', 'host', 'hostaddr', 'port', 'user', 'service')})
        require(params.get('dbname') == receipt['database']
                and params.get('host') == '127.0.0.1'
                and str(params.get('port')) == str(receipt['port'])
                and params.get('user') == receipt['user']
                and params.get('hostaddr', '127.0.0.1') == '127.0.0.1'
                and not params.get('service'), 'Blocked connection outside this disposable database.')
        conn = raw_connect(conninfo, **kwargs)
        return conn

    def verify_django(sender, connection, **kwargs):
        require(connection.alias == 'default' and connection.settings_dict['NAME'] == receipt['database'],
                'Unexpected Django database alias/name.')
        with connection.cursor() as cursor:
            cursor.execute("""SELECT current_database(), current_user, d.oid::bigint,
                shobj_description(d.oid, 'pg_database'),
                (SELECT system_identifier::text FROM pg_control_system())
                FROM pg_database d WHERE d.datname=current_database()""")
            require(cursor.fetchone() == (receipt['database'], receipt['user'], receipt['oid'],
                    'dic-fee-test:' + receipt['marker'], receipt['identity']['system_identifier']),
                    'Disposable connection identity mismatch.')

    def install():
        from django.db.backends.postgresql.base import DatabaseWrapper
        from django.db.backends.base.base import BaseDatabaseWrapper
        from django.db.backends.postgresql.creation import DatabaseCreation
        from django.db.backends.signals import connection_created
        original = BaseDatabaseWrapper.ensure_connection

        def only_disposable(wrapper):
            require(isinstance(wrapper, DatabaseWrapper) and wrapper.alias == 'default'
                    and wrapper.settings_dict['NAME'] == receipt['database'], 'Unexpected Django target.')
            return original(wrapper)

        def denied(*args, **kwargs):
            raise RuntimeError('Django database creation/cloning/deletion is disabled.')

        stack.enter_context(patch.object(BaseDatabaseWrapper, 'ensure_connection', only_disposable))
        for name in ('create_test_db', 'clone_test_db', 'destroy_test_db'):
            stack.enter_context(patch.object(DatabaseCreation, name, denied))
        connection_created.connect(verify_django, weak=False)

    def verify_empty():
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema')
                AND n.nspname NOT LIKE 'pg_toast%%' AND c.relkind IN ('r','p','v','m','S','f')""")
            require(cursor.fetchone() == (0,), 'New database is not empty; refusing migrations.')

    def verify_reuse():
        from django.apps import apps
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(connection)
        require(not loader.detect_conflicts(), 'Migration graph conflicts; refusing rerun.')
        loader.check_consistent_history(connection)
        require(set(loader.applied_migrations) == set(loader.graph.nodes),
                'Existing schema migration set differs; rerun never applies migrations.')
        require(('dic', '0034_approved_2026_fees') in loader.applied_migrations,
                'Approved fee migration missing; refusing rerun.')
        # A completed TestCase suite rolls back its business fixtures. Do not
        # flush evidence, clear dirty records, or attempt to repair this database.
        allowed = {'auth.Permission', 'contenttypes.ContentType'}
        for model in apps.get_models(include_auto_created=True):
            if model._meta.managed and not model._meta.proxy and model._meta.label not in allowed:
                require(not model._base_manager.using('default').exists(),
                        'Retained records in ' + model._meta.label + '; refusing rerun without resetting them.')
        print('Existing receipt-matched schema and clean fixtures verified; no migrate/flush/reset.', flush=True)

    config = dict(ENGINE='django.db.backends.postgresql', NAME=receipt['database'],
        HOST='127.0.0.1', PORT=str(receipt['port']), USER=receipt['user'], PASSWORD=password,
        CONN_MAX_AGE=0, OPTIONS={'connect_timeout': 5, 'sslmode': 'disable'},
        TEST={'NAME': receipt['database']})
    with ExitStack() as stack:
        stack.enter_context(patch.object(psycopg, 'connect', guarded_connect))
        stack.enter_context(patch.object(psycopg.Connection, 'connect', guarded_connect))
        previous = sys.argv
        sys.argv = [str(Path(__file__).with_name('test_dic_2026_fees.py'))]
        try:
            runpy.run_path(sys.argv[0], run_name='__main__', init_globals={
                'FEE_DATABASE': config, 'FEE_INSTALL_GUARDS': install, 'FEE_VERIFY_EMPTY': verify_empty,
                'FEE_REUSE': reuse, 'FEE_VERIFY_REUSE': verify_reuse})
        finally:
            sys.argv = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'run', 'rerun', 'cleanup'])
    parser.add_argument('--port', type=int)
    parser.add_argument('--user')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--approve-create', action='store_true')
    parser.add_argument('--approve-drop', action='store_true')
    parser.add_argument('--approve-test-writes', action='store_true')
    args = parser.parse_args()
    require(not args.approve_create or args.action == 'run', '--approve-create is only valid for run.')
    require(not args.approve_drop or args.action == 'cleanup', '--approve-drop is only valid for cleanup.')
    require(not args.approve_test_writes or args.action == 'rerun', '--approve-test-writes is only valid for rerun.')
    import psycopg
    from psycopg import sql
    if args.action == 'plan':
        require(args.plan and not args.plan.exists() and args.port and args.user,
                'New --plan path, explicit --port and --user required.')
        require(1 <= args.port <= 65535, 'Invalid port.')
        data = dict(host='127.0.0.1', port=args.port, user=args.user,
            database='test_dic_fees_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:12],
            marker=uuid.uuid4().hex)
        password = getpass.getpass('Local PostgreSQL role password (not saved): ')
        with connect(data, password, readonly=True) as conn:
            data['identity'] = identity(conn)
            require(data['identity']['user'] == data['user'], 'Role mismatch.')
            require(conn.execute('SHOW transaction_read_only').fetchone() == ('on',), 'Read-only preflight required.')
            require(conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone() == (True,),
                    'Role lacks CREATEDB; no privileges will be changed.')
            require(database_info(conn, data['database']) is None, 'Generated name already exists; stop.')
            data['baseline_oids'] = [row[0] for row in conn.execute('SELECT oid::bigint FROM pg_database')]
        save_new(args.plan, data)
        print('Read-only preflight passed. Review plan:', args.plan)
        print('Proposed new database:', data['database'])
        print('Server identity:', data['identity'])
        print('No database created. Explicit --approve-create is required next.')
        return 0
    if args.action == 'run':
        require(args.approve_create and args.plan and args.receipt and not args.receipt.exists(),
                'Explicit --approve-create, existing --plan and NEW --receipt path required.')
        data = load(args.plan)
    elif args.action == 'rerun':
        require(args.approve_test_writes and args.receipt,
                'Explicit --approve-test-writes and existing creation --receipt required.')
        data = load(args.receipt)
    else:
        require(args.approve_drop and args.receipt, 'Explicit --approve-drop and creation --receipt required.')
        data = load(args.receipt)
    password = getpass.getpass('Local PostgreSQL role password (not saved): ')
    with connect(data, password, readonly=False) as conn:
        verify_server(conn, data)
        require(conn.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (data['database'],)).fetchone() == (True,),
                'Another fee test operation holds this database lock.')
        if args.action == 'rerun':
            verify_created(conn, data)
            require(conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datid=%s', (data['oid'],)).fetchone() == (0,),
                    'Database has active connections; refusing concurrent rerun.')
            run_suite(data, password, reuse=True)
            return 0
        if args.action == 'cleanup':
            verify_created(conn, data)
            require(conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datid=%s', (data['oid'],)).fetchone() == (0,),
                    'Database still has connections; cleanup refuses to terminate sessions.')
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(data['database'])))
            print('Dropped only receipt-matched database:', data['database'], 'OID:', data['oid'])
            return 0
        require(database_info(conn, data['database']) is None, 'Database already exists; no reuse/reset/clone allowed.')
        # Reserve the evidence file before any writes; a failed run is never retried into this database.
        data['status'] = 'reserved'
        save_new(args.receipt, data)
        conn.execute(sql.SQL('CREATE DATABASE {} WITH TEMPLATE template0 OWNER {}').format(
            sql.Identifier(data['database']), sql.Identifier(data['user'])))
        row = database_info(conn, data['database'])
        require(row and row[0] != PROTECTED_OID and row[0] not in data['baseline_oids'] and row[1] == data['user'],
                'New database identity is unsafe; stop without cleanup.')
        data['oid'] = row[0]
        conn.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(
            sql.Identifier(data['database']), sql.Literal('dic-fee-test:' + data['marker'])))
        data['status'] = 'created'
        args.receipt.write_text(json.dumps(data, indent=2), encoding='utf-8')
        verify_created(conn, data)
        print('Created isolated database:', data['database'], 'OID:', data['oid'], flush=True)
        print('Receipt:', args.receipt, '; retained until separately approved cleanup.', flush=True)
        run_suite(data, password)
    return 0
