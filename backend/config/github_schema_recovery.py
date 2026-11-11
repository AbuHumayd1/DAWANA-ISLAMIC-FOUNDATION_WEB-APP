"""Manual Actions recovery only. Never imported by application startup."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request


STAGE = 'manual request validation'


class Stop(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Stop(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(value, key):
    return hmac.new(key, json.dumps(value, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def process(command, env=None):
    result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=900)
    require(result.returncode == 0, 'PostgreSQL tool failed; operation stopped.')


def tool(command, pg_env):
    command_line = ['docker', 'exec']
    for name in pg_env:
        command_line.extend(['--env', name])
    process([*command_line, os.environ['RESTORE_CONTAINER'], *command],
            env={**os.environ, **pg_env})


def crypt_file(source, destination, key, decrypt=False):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    with source.open('rb') as incoming, destination.open('xb') as output:
        os.chmod(destination, 0o600)
        if decrypt:
            nonce = incoming.read(12)
            incoming.seek(-16, 2)
            tag = incoming.read(16)
            remaining = source.stat().st_size - 28
            require(remaining >= 0, 'Invalid encrypted backup.')
            incoming.seek(12)
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        else:
            nonce = os.urandom(12)
            output.write(nonce)
            remaining = source.stat().st_size
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        cipher.authenticate_additional_data(b'dawana-schema-backup-v1')
        while remaining:
            block = incoming.read(min(1024 * 1024, remaining))
            require(bool(block), 'Truncated backup.')
            output.write(cipher.update(block))
            remaining -= len(block)
        output.write(cipher.finalize())
        if not decrypt:
            output.write(cipher.tag)


def restore_backup(archive, roles):
    """The restore target is fixed to a disposable loopback-only service."""
    import psycopg
    from psycopg import sql

    local = dict(host='127.0.0.1', port=5432, dbname='recovery_restore',
                 user='postgres', password='isolated-restore-only', sslmode='disable')
    with psycopg.connect(**local, autocommit=True) as connection:
        require(connection.info.host == '127.0.0.1' and connection.info.dbname == 'recovery_restore',
                'Isolated restore target mismatch.')
        for role in roles:
            if not connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', [role]).fetchone():
                connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
    process(['docker', 'cp', str(archive), os.environ['RESTORE_CONTAINER'] + ':/tmp/recovery.dump'])
    # Clean only the fixed disposable database; handles its pre-existing public schema.
    tool(['pg_restore', '--clean', '--if-exists', '--exit-on-error', '--single-transaction', '--dbname=recovery_restore',
          '/tmp/recovery.dump'], dict(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres',
                                     PGPASSWORD='isolated-restore-only', PGSSLMODE='disable'))
    # An actual restore, preserving ownership and ACLs, must finish successfully.
    with psycopg.connect(**local) as connection:
        require(connection.execute('SELECT current_database()').fetchone()[0] == 'recovery_restore',
                'Restore verification failed.')


def api_run(run_id):
    require(bool(re.fullmatch(r'[1-9][0-9]*', run_id)), 'Invalid preflight run ID.')
    url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def initialize_environment():
    for name in list(os.environ):
        if name.startswith('PG'):
            del os.environ[name]
    values = json.loads(os.environ['RECOVERY_DJANGO_ENV'])
    require(isinstance(values, dict) and all(isinstance(k, str) and isinstance(v, str)
                                           for k, v in values.items()), 'Invalid settings secret.')
    for name, value in values.items():
        require(bool(re.fullmatch(
            r'(?:DJANGO_|DB_|DIC_|PAYSTACK_|EMAIL_|RESEND_|FOUNDATION_|AWS_)[A-Z0-9_]+'
            r'|DATABASE_URL|FRONTEND_ORIGIN|PUBLIC_HOST|DEFAULT_FROM_EMAIL', name)),
            'Unexpected settings key.')
        # Mask individual values too: the JSON secret's automatic mask is insufficient.
        masked = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        if masked and (re.search('SECRET|PASSWORD|TOKEN|KEY|DATABASE_URL', name) or '://' in value):
            print('::add-mask::' + masked, flush=True)
        os.environ[name] = value
    require(os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.render') == 'config.settings.render',
            'Render settings required.')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
    sys.path.insert(0, str(Path.cwd()))
    from django.conf import settings
    require(settings.PAYSTACK_MODE == 'test' and not settings.PAYSTACK_LIVE_ENABLED,
            'Initialization requires the existing pre-live payment configuration.')
    from django.db import connection
    config = settings.DATABASES['default']
    require(config['OPTIONS'].get('sslmode') == 'verify-full', 'verify-full required.')
    config['OPTIONS'] = dict(config['OPTIONS'])
    original_options = config['OPTIONS'].get('options', '')
    config['OPTIONS']['options'] = (original_options +
        ' -c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=2000').strip()
    config['OPTIONS']['connect_timeout'] = 5
    import django
    django.setup()
    return settings, connection, values, original_options


def manifest_now(connection, settings):
    from django.db.migrations.executor import MigrationExecutor
    from config.release_migrations import plan_manifest

    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    require(not executor.loader.detect_conflicts(), 'Migration graph conflict.')
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    identity = dict(database='dawana_db', host=os.environ['RECOVERY_EXPECTED_HOST'], port='5432',
                    role='dawana_db_user', cluster_id=os.environ['RECOVERY_EXPECTED_CLUSTER_ID'])
    return plan_manifest(executor.loader, plan, 'dawana_db', settings.SETTINGS_MODULE, identity)


def cache_plan():
    from django.core.management import call_command

    output = io.StringIO()
    call_command('createcachetable', 'dawana_release_cache', database='default',
                 dry_run=True, stdout=output)
    sql = output.getvalue()
    require(sql.startswith('CREATE TABLE "dawana_release_cache" (') and sql.count('CREATE ') == 2,
            'Unexpected cache plan.')
    return sql


def verify_initialized(connection):
    from django.apps import apps
    from django.core.management import call_command

    call_command('migrate', check=True, interactive=False, stdout=io.StringIO())
    with connection.cursor() as cursor:
        cursor.execute('SELECT cache_key,value,expires FROM dawana_release_cache LIMIT 0')
        cursor.execute("""
            SELECT has_table_privilege('dawana_release_cache','SELECT'),
                   has_table_privilege('dawana_release_cache','INSERT'),
                   has_table_privilege('dawana_release_cache','UPDATE'),
                   has_table_privilege('dawana_release_cache','DELETE')
        """)
        require(all(cursor.fetchone()), 'Cache privileges incomplete.')
        for name in ('CampEdition', 'RegistrationCategory', 'PromoVideo', 'CampFlyer',
                     'Lecturer', 'LecturerAppearance', 'CampActivity'):
            model = apps.get_model('dic', name)
            query, params = model.objects.all().query.get_compiler(using='default').as_sql()
            cursor.execute(f'SELECT * FROM ({query}) AS verification LIMIT 0', params)
        edition = apps.get_model('dic', 'CampEdition')
        require(not edition.objects.filter(is_active=True).exists() and
                not edition.objects.filter(registration_status='open').exists(),
                'Unexpected active edition or open registration.')


def run():
    global STAGE
    phase = os.environ['PHASE']
    require(phase in ('PREFLIGHT', 'INITIALIZE') and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'Manual dispatch required.')
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Automatic reruns forbidden.')
    require(os.environ.get('RECOVERY_POSTGRES_MAJOR') in ('17', '18'),
            'Select a verified supported PostgreSQL major.')
    key = base64.b64decode(os.environ['RECOVERY_BACKUP_KEY'], validate=True)
    require(len(key) == 32, 'Backup key must decode to 32 bytes.')
    STAGE = 'production settings validation'
    settings, connection, secret_values, original_options = initialize_environment()
    from config.schema_recovery_preflight import main as fresh_gate
    from django.core.management import call_command
    from django.db import transaction

    work = Path(os.environ['RUNNER_TEMP']) / 'schema-recovery'
    evidence_dir = work / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive = work / 'backup.dump'
    encrypted = evidence_dir / 'backup.enc'
    STAGE = 'read-only identity and cross-schema preflight'
    fresh_gate()  # Closes its read-only connection. No existing application schema may proceed.
    connection.close()
    STAGE = 'source-hashed migration and cache planning'
    manifest = manifest_now(connection, settings)
    cache_sql = cache_plan()
    expected_settings = signature(secret_values, key)
    evidence = None
    if phase == 'INITIALIZE':
        STAGE = 'approved preflight provenance and evidence verification'
        require(os.environ.get('APPROVAL') == 'INITIALIZE dawana_db', 'Explicit approval missing.')
        run_info = api_run(os.environ['PREFLIGHT_RUN'])
        require(run_info['conclusion'] == 'success' and run_info['event'] == 'workflow_dispatch' and
                run_info['head_sha'] == os.environ['GITHUB_SHA'] and
                run_info['path'] == '.github/workflows/production-schema-recovery.yml' and
                run_info['run_attempt'] == 1, 'Preflight provenance mismatch.')
        evidence = json.loads((evidence_dir / 'evidence.json').read_text())
        supplied_signature = evidence.pop('signature')
        require(hmac.compare_digest(supplied_signature, signature(evidence, key)),
                'Evidence authentication failed.')
        require(evidence['phase'] == 'PREFLIGHT' and evidence['run_id'] == os.environ['PREFLIGHT_RUN'] and
                evidence['commit'] == os.environ['GITHUB_SHA'] and
                evidence['repository'] == os.environ['GITHUB_REPOSITORY'] and
                evidence['settings_hmac'] == expected_settings and
                evidence['manifest'] == manifest and
                json.loads((evidence_dir / 'manifest.json').read_text()) == manifest and
                evidence['cache_sql'] == cache_sql and
                (evidence_dir / 'cache.sql').read_text() == cache_sql and
                str(evidence['postgres_major']) == os.environ['RECOVERY_POSTGRES_MAJOR'] and
                evidence['restore_verified'] is True, 'Approved evidence differs from target or source.')
        require(manifest['plan_sha256'] == os.environ['PLAN_HASH'] and
                digest(encrypted) == evidence['backup_sha256'] == os.environ['BACKUP_HASH'],
                'Approved manifest or backup hash mismatch.')
        crypt_file(encrypted, archive, key, decrypt=True)
        require(digest(archive) == evidence['plaintext_sha256'], 'Backup checksum mismatch.')
        STAGE = 'isolated restore of approved backup'
        restore_backup(archive, evidence['roles'])
    else:
        STAGE = 'read-only full production backup'
        config = connection.settings_dict
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SHOW server_version_num')
            server_major = int(cursor.fetchone()[0]) // 10000
            require(str(server_major) == os.environ['RECOVERY_POSTGRES_MAJOR'],
                    'PostgreSQL client/restore major must match the production server.')
            cursor.execute('SELECT rolname FROM pg_roles')
            roles = [row[0] for row in cursor.fetchall()]
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot = cursor.fetchone()[0]
            process(['docker', 'cp', config['OPTIONS']['sslrootcert'],
                     os.environ['RESTORE_CONTAINER'] + ':/tmp/recovery-ca.pem'])
            pg_env = dict(PGHOST=config['HOST'], PGPORT=str(config['PORT'] or '5432'),
                          PGDATABASE=config['NAME'], PGUSER=config['USER'],
                          PGPASSWORD=config['PASSWORD'], PGSSLMODE='verify-full',
                          PGSSLROOTCERT='/tmp/recovery-ca.pem',
                          PGCHANNELBINDING=config['OPTIONS'].get('channel_binding', 'prefer'),
                          PGOPTIONS='-c default_transaction_read_only=on',
                          PGCONNECT_TIMEOUT='5')
            tool(['pg_dump', '--format=custom', '--snapshot=' + snapshot,
                  '--file=/tmp/recovery.dump'], pg_env)
        process(['docker', 'cp', os.environ['RESTORE_CONTAINER'] + ':/tmp/recovery.dump', str(archive)])
        os.chmod(archive, 0o600)
        STAGE = 'isolated backup restore test'
        restore_backup(archive, roles)
        crypt_file(archive, encrypted, key)
        evidence = dict(phase='PREFLIGHT', run_id=os.environ['GITHUB_RUN_ID'],
                        repository=os.environ['GITHUB_REPOSITORY'], commit=os.environ['GITHUB_SHA'],
                        settings_hmac=expected_settings, manifest=manifest, cache_sql=cache_sql,
                        roles=roles, postgres_major=server_major, restore_verified=True,
                        plaintext_sha256=digest(archive), backup_sha256=digest(encrypted))
        evidence['signature'] = signature(evidence, key)
        (evidence_dir / 'evidence.json').write_text(json.dumps(evidence, indent=2))
        (evidence_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        (evidence_dir / 'cache.sql').write_text(cache_sql)
        print('PREFLIGHT passed: backup restored in isolation; production remains read-only.')
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
            summary.write(f"Preflight run {os.environ['GITHUB_RUN_ID']}\n\n"
                          f"Commit: {os.environ['GITHUB_SHA']}\n\n"
                          f"Plan SHA-256: {manifest['plan_sha256']}\n\n"
                          f"Encrypted backup SHA-256: {evidence['backup_sha256']}\n\n"
                          "Actual isolated restore passed. Review artifact before INITIALIZE.\n")
        return

    # No production write has occurred above. Revalidate immediately before application.
    STAGE = 'final identity and fresh-schema verification'
    fresh_gate()
    connection.close()
    config = settings.DATABASES['default']
    config['OPTIONS']['options'] = (original_options + ' -c lock_timeout=5000').strip()
    # Keep one database session locked across all migrations and cache creation.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(184740211, 2)')
        require(cursor.fetchone()[0], 'Another initializer holds the database lock.')
    try:
        fresh_gate(close_connection=False)
        config['OPTIONS']['options'] = (original_options + ' -c lock_timeout=5000').strip()
        require(manifest_now(connection, settings) == manifest, 'Migration plan changed.')
        approval = dict(manifest=manifest, approved_by=os.environ['GITHUB_ACTOR'],
                        approved_at=datetime.now(timezone.utc).isoformat(),
                        backup_reference=f"Actions run {evidence['run_id']}: {evidence['backup_sha256']}",
                        restore_procedure='Restore the encrypted full archive using the retained key; isolated restore passed twice.',
                        rollback_decision='Stop on failure; inspect remaining plan. No automatic reversal or retry.')
        approval_file = work / 'approval.json'
        approval_file.write_text(json.dumps(approval))
        STAGE = 'approved migration application'
        call_command('release_migrations', settings='config.settings.render', database_name='dawana_db',
                     hostname=os.environ['RECOVERY_EXPECTED_HOST'], port='5432', role='dawana_db_user',
                     cluster_id=os.environ['RECOVERY_EXPECTED_CLUSTER_ID'], approval_file=str(approval_file),
                     apply_approved_plan=True, stdout=io.StringIO())
        STAGE = 'approved cache creation'
        call_command('createcachetable', 'dawana_release_cache', database='default', stdout=io.StringIO())
        STAGE = 'post-initialization verification'
        verify_initialized(connection)
        print('INITIALIZE completed: migration history, cache and required tables verified; registration remains inactive.')
    finally:
        connection.close()  # Also releases the session lock.


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        cause = exc
        while cause.__cause__ is not None:
            cause = cause.__cause__
        state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        state = state if isinstance(state, str) and re.fullmatch('[0-9A-Z]{5}', state) else None
        print(json.dumps({'recovery': 'STOP', 'stage': STAGE, 'reason': str(exc) if isinstance(exc, Stop)
                          else 'Operation failed; no automatic retry.', 'sqlstate': state}), flush=True)
        sys.exit(1)
