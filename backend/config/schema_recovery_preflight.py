"""Read-only fresh-database gate. Run from backend with Render settings."""
import json
import os
from pathlib import Path
import re
import sys


def main(close_connection=True):
    sys.path.insert(0, str(Path.cwd()))
    from django.conf import settings

    if settings.SETTINGS_MODULE != 'config.settings.render':
        raise RuntimeError('Explicit Render settings required.')
    host = os.environ['RECOVERY_EXPECTED_HOST']
    schema = os.environ['RECOVERY_EXPECTED_SCHEMA']
    cluster = os.environ['RECOVERY_EXPECTED_CLUSTER_ID']
    if not host or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema) or not cluster.isdecimal():
        raise RuntimeError('Explicit host, schema and cluster identity required.')
    config = settings.DATABASES['default']
    if (config['ENGINE'] != 'django.db.backends.postgresql'
            or (config['NAME'], config['USER'], str(config['PORT'] or '5432'), config['HOST'])
            != ('dawana_db', 'dawana_db_user', '5432', host)
            or config['OPTIONS'].get('sslmode') != 'verify-full'):
        raise RuntimeError('Configured identity or TLS mismatch.')
    config['OPTIONS'] = dict(config['OPTIONS'])
    config['OPTIONS']['options'] = (
        config['OPTIONS'].get('options', '') +
        ' -c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=2000'
    ).strip()
    config['OPTIONS']['connect_timeout'] = 5
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection, transaction

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute("""
                SELECT current_database(), session_user, current_user, current_schema(),
                       system_identifier::text, current_setting('transaction_read_only')
                FROM pg_control_system()
            """)
            if cursor.fetchone() != ('dawana_db', 'dawana_db_user', 'dawana_db_user', schema, cluster, 'on'):
                raise RuntimeError('Connected identity mismatch.')
            tables = {'django_migrations', 'dawana_release_cache'}
            for model in apps.get_models(include_auto_created=True):
                if model._meta.managed:
                    tables.add(model._meta.db_table)
            # pg_catalog sees objects outside search_path, including inaccessible schemas.
            cursor.execute("""
                SELECT n.nspname,c.relname,c.relkind,
                       has_schema_privilege(n.oid,'USAGE'),
                       pg_table_is_visible(c.oid)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema')
                  AND n.nspname NOT LIKE 'pg_toast%%'
                  AND (c.relname = ANY(%s) OR c.relname LIKE 'dic_%%'
                       OR c.relname LIKE 'accounts_%%' OR c.relname LIKE 'django_%%'
                       OR c.relname LIKE 'auth_%%')
                ORDER BY n.nspname,c.relname
            """, [sorted(tables)])
            objects = cursor.fetchall()
            print(json.dumps({'application_objects_all_schemas': objects}), flush=True)
            cursor.execute("""
                SELECT n.nspname,p.proname
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname NOT IN ('pg_catalog','information_schema')
                  AND (p.proname LIKE 'dic_%%' OR p.proname LIKE 'accounts_%%')
                ORDER BY n.nspname,p.proname
            """)
            functions = cursor.fetchall()
            cursor.execute("""
                SELECT n.nspname,c.relname,t.tgname
                FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE NOT t.tgisinternal
                  AND (t.tgname LIKE 'dic_%%' OR t.tgname LIKE 'accounts_%%')
                ORDER BY n.nspname,c.relname,t.tgname
            """)
            triggers = cursor.fetchall()
            print(json.dumps({'application_functions_all_schemas': functions,
                              'application_triggers_all_schemas': triggers}), flush=True)
            if objects or functions or triggers:
                raise RuntimeError('Existing Django objects found. Fresh initialization refused.')
            cursor.execute("""
                SELECT has_schema_privilege(%s,'USAGE'),
                       has_schema_privilege(%s,'CREATE')
            """, [schema, schema])
            if cursor.fetchone() != (True, True):
                raise RuntimeError('Target schema privileges insufficient.')
            print(json.dumps({'fresh_gate': 'PASS', 'schema': schema}), flush=True)
            transaction.set_rollback(True)
    finally:
        if close_connection:
            connection.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        cause = exc.__cause__ or exc
        state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        if not isinstance(state, str) or not re.fullmatch(r'[0-9A-Z]{5}', state):
            state = None
        # Never print exception text, environment contents or connection strings.
        print(json.dumps({'fresh_gate': 'STOP', 'sqlstate': state}), flush=True)
        sys.exit(1)
