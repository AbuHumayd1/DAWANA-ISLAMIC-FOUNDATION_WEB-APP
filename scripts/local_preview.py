"""Prepare and serve the verified local development database only."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import secrets
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
STATE = ROOT / '.local-preview'


class StopPreview(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise StopPreview(message)


def configure():
    import environ
    environ.Env.read_env(BACKEND / '.env')
    env = environ.Env()
    STATE.mkdir(exist_ok=True)
    diagnostic_file = STATE / 'diagnostic-token'
    if not diagnostic_file.exists():
        try:
            with diagnostic_file.open('x', encoding='ascii') as handle:
                handle.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    os.environ['DAWANA_LOCAL_DIAGNOSTIC_TOKEN'] = diagnostic_file.read_text(encoding='ascii').strip()
    if env('DATABASE_URL', default=''):
        db = env.db_url('DATABASE_URL')
        require(db['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL is required.')
        target = dict(host=db.get('HOST') or '127.0.0.1', port=str(db.get('PORT') or '5432'),
                      user=db.get('USER') or '', password=db.get('PASSWORD') or '', name=db['NAME'])
    else:
        target = dict(host=env('DB_HOST', default='127.0.0.1'), port=env('DB_PORT', default='5432'),
                      user=env('DB_USER'), password=env('DB_PASSWORD', default=''), name=env('DB_NAME'))
    require(target['host'].lower() in ('localhost', '127.0.0.1', '::1'), 'Refusing a non-loopback database.')
    name = target['name'].lower()
    require(not name.startswith('test_') and 'prod' not in name and 'stag' not in name and
            name not in ('postgres', 'template0', 'template1'), 'Refusing a test, production, staging or maintenance database.')
    os.environ.update(DATABASE_URL='', DB_NAME=target['name'], DB_USER=target['user'],
                      DB_PASSWORD=target['password'], DB_HOST=target['host'], DB_PORT=target['port'],
                      DJANGO_SETTINGS_MODULE='config.settings.development', DJANGO_DEBUG='True',
                      DJANGO_ALLOWED_HOSTS='127.0.0.1,localhost',
                      DJANGO_CORS_ALLOWED_ORIGINS='http://127.0.0.1:5173,http://localhost:5173',
                      DJANGO_CSRF_TRUSTED_ORIGINS='http://127.0.0.1:5173,http://localhost:5173',
                      DIC_MEMORY_STORAGE='local', DIC_MEMORY_S3_BUCKET='', DIC_MEMORY_S3_ENDPOINT='',
                      DIC_EMAIL_RECOVERY_ENABLED='False', DIC_RECOVERY_DELIVERY_WORKER_ENABLED='False',
                      DIC_SMS_RECOVERY_ADAPTER='', DIC_WHATSAPP_ACCESS_TOKEN='',
                      EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PAYSTACK_MODE='test')
    if not os.environ.get('PAYSTACK_SECRET_KEY', '').startswith('sk_test_'):
        os.environ['PAYSTACK_SECRET_KEY'] = ''
    sys.path.insert(0, str(BACKEND))
    return target


def setup(target):
    import django
    django.setup()
    from django.conf import settings
    actual = settings.DATABASES['default']
    require(actual['NAME'] == target['name'] and actual['HOST'] == target['host'] and
            str(actual['PORT']) == target['port'], 'Django resolved an unexpected database.')


def backup_database(target, major, requested_dump=''):
    """Create and read-check a new archive; never restore or remove an archive."""
    def diagnostic(value):
        if isinstance(value, bytes):
            value = value.decode(errors='replace')
        value = str(value)
        # Diagnostics are useful, but authentication material must stay private.
        value = re.sub(r'(?i)postgres(?:ql)?://[^\s]+', '[redacted connection URL]', value)
        value = re.sub(r'(?i)(password\s*[=:]\s*)(?:\x27[^\x27]*\x27|"[^"]*"|\S+)',
                       r'\1[redacted]', value)
        secrets = [target.get('password', ''), target.get('user', '')]
        secrets.extend(v for k, v in os.environ.items()
                       if any(token in k.upper() for token in ('PASSWORD', 'SECRET', 'TOKEN', 'ACCESS_KEY', 'DATABASE_URL')))
        variants = {variant for secret in secrets if secret
                    for variant in (secret, quote(secret, safe=''), quote_plus(secret))}
        for secret in sorted(variants, key=len, reverse=True):
            value = value.replace(secret, '[redacted]')
        return value.strip()

    # Do not inherit libpq service files, alternate hosts, options or credentials.
    child = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')}
    child.update(PGPASSWORD=target['password'], PGCONNECT_TIMEOUT='10', PGAPPNAME='dawana-local-backup')

    def run(command, label):
        try:
            result = subprocess.run(command, env=child, capture_output=True)
        except OSError as error:
            raise StopPreview(f'{label} could not start: {diagnostic(error)}. No migration applied.') from None
        require(result.returncode == 0,
                f'{label} failed (exit {result.returncode}): '
                f'{diagnostic(result.stderr) or "No error text returned"}. No migration applied.')
        return result

    installed = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PostgreSQL' / str(major) / 'bin' / 'pg_dump.exe'
    dump = requested_dump or (str(installed) if installed.is_file() else shutil.which('pg_dump'))
    require(dump and Path(dump).is_file(), 'pg_dump unavailable: supply -PgDumpPath. No migration applied.')
    dump = Path(dump).resolve()
    restore = dump.with_name('pg_restore.exe' if os.name == 'nt' else 'pg_restore')
    require(restore.is_file(), 'Matching pg_restore required to verify backup. No migration applied.')
    versions = []
    for executable in (dump, restore):
        result = run([str(executable), '--version'], executable.name + ' version check')
        match = re.search(rb'\(PostgreSQL\)\s+(\d+)(?:\.(\d+))?', result.stdout)
        require(match, 'Unrecognized PostgreSQL tool version. No migration applied.')
        versions.append(match.group(0))
        require(int(match.group(1)) == major,
                f'{executable.name} must match server major {major}; supply -PgDumpPath. No migration applied.')
    require(versions[0] == versions[1], 'pg_dump/pg_restore versions differ. No migration applied.')
    print(f'Backup tool: {dump} ({versions[0].decode()})', flush=True)
    archive = STATE / ('development-' + uuid.uuid4().hex + '.dump')
    # Reserve the unique path exclusively; never overwrite an existing backup.
    with archive.open('xb'):
        pass
    run([str(dump), '--format=custom', '--no-password', '--host', target['host'],
         '--port', target['port'], '--username', target['user'], '--file', str(archive),
         '--dbname', target['name']], 'pg_dump')
    require(archive.is_file() and archive.stat().st_size > 5,
            'pg_dump produced a missing/empty archive. No migration applied.')
    with archive.open('rb') as handle:
        require(handle.read(5) == b'PGDMP', 'Invalid custom archive header. No migration applied.')
    result = run([str(restore), '--list', str(archive)], 'pg_restore archive verification')
    require(result.stdout.strip(), 'Backup table of contents is empty. No migration applied.')
    # Force a complete local archive read, without connecting to any database.
    run([str(restore), '--file', os.devnull, str(archive)], 'pg_restore full archive read')
    print(f'Verified local backup: {archive} ({archive.stat().st_size} bytes)', flush=True)
    return archive


def prepare(target, args):
    import psycopg
    from django.core.management import call_command
    from django.db import connection
    from django.apps import apps
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    with psycopg.connect(host=target['host'], port=target['port'], user=target['user'],
                         password=target['password'], dbname=target['name'], connect_timeout=5,
                         options='-c default_transaction_read_only=on') as conn:
        major = int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000
    print(f"LOCAL TARGET: {target['host']}:{target['port']} / {target['name']} (PostgreSQL {major})", flush=True)
    setup(target)
    call_command('check', verbosity=0)
    executor = MigrationExecutor(connection)
    require(('dic', '0021_promovideo_campflyer') in executor.loader.graph.nodes, 'Migration 0021 missing.')
    changes = MigrationAutodetector(executor.loader.project_state(), ProjectState.from_apps(apps)).changes(graph=executor.loader.graph)
    require(not changes, 'Model/migration drift: review before migrating.')
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    print('Pending: ' + (', '.join(f'{m.app_label}.{m.name}' for m, backwards in pending) or 'none'), flush=True)
    STATE.mkdir(exist_ok=True)
    if pending:
        require(not any(backwards for m, backwards in pending), 'Unexpected backwards migration.')
        confirmation = args.database or input('Type the exact LOCAL database name to authorize backup and these migrations: ').strip()
        require(confirmation == target['name'], 'Target confirmation mismatch; no migration applied.')
        backup_database(target, major, args.pg_dump)
        call_command('migrate', interactive=False, verbosity=1)
    call_command('migrate', '--check', verbosity=0)
    from django.contrib import admin
    from django.contrib.auth import get_user_model
    from dic.models import CampPhotograph, PromoVideo, Lecturer, LecturerAppearance, CampActivity, CampFlyer, CampVideo, GuardianRelationship, HousingJob, House, HouseAllocation, CampEnrollment, DigitalIDIssue
    for model in (CampPhotograph, PromoVideo, Lecturer, LecturerAppearance, CampActivity, CampFlyer, CampVideo, GuardianRelationship, HousingJob, House, HouseAllocation, CampEnrollment, DigitalIDIssue):
        require(model in admin.site._registry, 'A required DIC model is absent from Admin.')
        print('Admin: ' + model.__name__ + ' -> /admin/dic/' + model._meta.model_name + '/')
    print('Active local superuser exists: ' + str(get_user_model().objects.filter(is_active=True, is_superuser=True).exists()))
    print('ffprobe available: ' + str(bool(shutil.which(os.environ.get('DIC_FFPROBE_BINARY', 'ffprobe')))))
    print('Media storage is local/private. No R2 requests. Use approved content and publishing permissions.')
    (STATE / 'prepared.json').write_text(json.dumps({k: target[k] for k in ('host', 'port', 'name')}), encoding='utf-8')
    connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'serve', 'create-admin'))
    parser.add_argument('--database', default='')
    parser.add_argument('--pg-dump', default='')
    parser.add_argument('--require-database', default='dawana_dev')
    parser.add_argument('--no-migrations', action='store_true')
    args = parser.parse_args()
    target = configure()
    if args.mode == 'prepare':
        require(target['name'] == args.require_database, 'Expected local dawana_dev database was not selected; no migration applied.')
        if args.no_migrations:
            setup(target)
            from django.core.management import call_command
            call_command('check', verbosity=0)
            call_command('migrate', '--check', verbosity=0)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                require(cursor.fetchone()[0] == 'dawana_dev', 'Connected database is not dawana_dev.')
            (STATE / 'prepared.json').write_text(json.dumps({k: target[k] for k in ('host', 'port', 'name')}), encoding='utf-8')
            print('Read-only development preparation passed: dawana_dev; no migrations or data writes performed.')
            return
        prepare(target, args)
    else:
        require((STATE / 'prepared.json').is_file(), 'Run local preparation first.')
        saved = json.loads((STATE / 'prepared.json').read_text(encoding='utf-8'))
        require(all(saved[k] == target[k] for k in saved), 'Database changed after preparation.')
        setup(target)
        from django.core.management import call_command
        if args.mode == 'create-admin':
            call_command('createsuperuser', interactive=True)
        else:
            call_command('runserver', '127.0.0.1:8000', use_reloader=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = str(error) if isinstance(error, StopPreview) else type(error).__name__ + ': local prerequisite failed; no credentials emitted.'
        print('STOP: ' + message, file=sys.stderr)
        sys.exit(1)
