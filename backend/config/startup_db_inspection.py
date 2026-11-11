"""Opt-in metadata and zero-row database probes, isolated from Gunicorn."""
import json
import os
from pathlib import Path
import re
import sys


def report(section, **values):
    print(json.dumps({'diagnostic': 'startup_db', 'section': section, **values}), flush=True)


def safe_error(exc):
    cause = exc
    while cause.__cause__ is not None:
        cause = cause.__cause__
    state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
    result = {'sqlstate': state if isinstance(state, str) and re.fullmatch('[0-9A-Z]{5}', state) else None}
    diag = getattr(cause, 'diag', None)
    for field in ('schema', 'table', 'column'):
        value = getattr(diag, field + '_name', None)
        if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$.]*', value):
            result[field] = value
    patterns = {
        '42P01': r'relation "([A-Za-z_][A-Za-z0-9_$.]*)" does not exist',
        '42703': r'column "?([A-Za-z_][A-Za-z0-9_$.]*)"? does not exist',
        '42501': r'permission denied for (?:table|relation|schema) ([A-Za-z_][A-Za-z0-9_$.]*)',
    }
    pattern = patterns.get(result['sqlstate'])
    match = re.fullmatch(pattern, getattr(diag, 'message_primary', '') or '') if pattern else None
    if match:
        result['object'] = match[1]
    return result


def inspect():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from django.conf import settings

    if settings.SETTINGS_MODULE != 'config.settings.render':
        report('stopped', reason='Render settings required')
        return
    config = settings.DATABASES['default']
    if config['ENGINE'] != 'django.db.backends.postgresql' or config['OPTIONS'].get('sslmode') != 'verify-full':
        report('stopped', reason='PostgreSQL verify-full required')
        return
    config['OPTIONS'] = dict(config['OPTIONS'])
    config['OPTIONS']['connect_timeout'] = 3
    config['OPTIONS']['options'] = (
        config['OPTIONS'].get('options', '') +
        ' -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=1000'
    ).strip()
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection, transaction

    def query(label, sql, params=(), metadata=False):
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall() if metadata else None
            report(label, ok=True, **({'metadata': rows} if metadata else {}))
        except Exception as exc:
            report(label, ok=False, **safe_error(exc))

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()[0] != 'on':
                report('stopped', reason='Read-only transaction required')
                return
            query('identity', """
                SELECT current_database(), session_user, current_user, current_schema(),
                       current_schemas(true), current_setting('search_path')
            """, metadata=True)
            query('cluster', 'SELECT system_identifier::text FROM pg_control_system()', metadata=True)
            query('cache_relations', """
                SELECT n.nspname, c.relkind, pg_table_is_visible(c.oid),
                       has_schema_privilege(n.oid, 'USAGE'),
                       has_table_privilege(c.oid, 'SELECT'),
                       has_table_privilege(c.oid, 'INSERT'),
                       has_table_privilege(c.oid, 'UPDATE'),
                       has_table_privilege(c.oid, 'DELETE')
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relname='dawana_release_cache'
            """, metadata=True)
            query('cache_columns', """
                SELECT n.nspname, a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relname='dawana_release_cache' AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY n.nspname,a.attnum
            """, metadata=True)
            query('cache_read', 'SELECT cache_key, value, expires FROM dawana_release_cache LIMIT 0')
            query('migration_history', """
                SELECT app,name FROM django_migrations
                WHERE app IN ('dic','accounts') ORDER BY app,name
            """, metadata=True)
            # Compile model columns without evaluating querysets or retrieving records.
            for name in ('CampEdition', 'RegistrationCategory', 'PromoVideo', 'CampFlyer',
                         'Lecturer', 'LecturerAppearance', 'CampActivity'):
                model = apps.get_model('dic', name)
                sql, params = model.objects.all().query.get_compiler(using='default').as_sql()
                query(model._meta.db_table, f'SELECT * FROM ({sql}) AS inspection LIMIT 0', params)
            for name, related in (('PromoVideo', ('edition',)), ('CampFlyer', ('edition',)),
                                  ('LecturerAppearance', ('lecturer', 'edition')),
                                  ('CampActivity', ('edition',))):
                model = apps.get_model('dic', name)
                sql, params = model.objects.select_related(*related).query.get_compiler(using='default').as_sql()
                query(name + '_joins', f'SELECT * FROM ({sql}) AS inspection LIMIT 0', params)
            transaction.set_rollback(True)
    finally:
        connection.close()


def main():
    if os.environ.get('DAWANA_STARTUP_DB_INSPECTION') != '1':
        return
    try:
        inspect()
    except Exception as exc:
        report('incomplete', **safe_error(exc))


if __name__ == '__main__':
    main()
