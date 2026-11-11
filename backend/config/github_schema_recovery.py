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
import shutil
import subprocess
import sys
import tempfile
import urllib.request


STAGE = 'manual request validation'


class Stop(Exception):
    pass


class ToolFailure(Stop):
    def __init__(self, tool_name, exit_status, category):
        super().__init__('PostgreSQL tool failed; operation stopped.')
        self.diagnostic = dict(tool=tool_name if tool_name in ('pg_dump', 'pg_restore', 'initdb', 'pg_ctl', 'psql', 'native_cluster') else 'unknown',
                               exit_status=exit_status if type(exit_status) is int else None,
                               category=category if category in {
                                   'version_mismatch', 'version_unrecognized', 'tls_trust_store',
                                   'tls_verification', 'authentication', 'database_permissions', 'snapshot',
                                   'executable_unavailable', 'timeout', 'connection',
                                   'filesystem', 'unclassified', 'process_start_failed'} else 'unclassified')


def tool_error_category(stderr):
    # Classify only. Never return stderr, paths, identifiers or exception text.
    message = stderr.lower()
    for category, fragments in (
        ('version_mismatch', ('server version mismatch', 'unsupported version in file header')),
        ('tls_trust_store', ('root certificate file', 'could not read root certificate', 'could not load root certificate')),
        ('tls_verification', ('certificate verify failed', 'server certificate', 'ssl error', 'ssl connection')),
        ('authentication', ('password authentication failed', 'no password supplied', 'no pg_hba.conf entry')),
        ('database_permissions', ('permission denied for', 'must be owner', 'row-level security')),
        ('snapshot', ('invalid snapshot identifier', 'could not import the requested snapshot')),
        ('executable_unavailable', ('executable file not found', 'executable not found', 'command not found')),
        ('timeout', ('timeout expired', 'connection timed out', 'statement timeout', 'lock timeout')),
        ('connection', ('could not translate host name', 'could not connect to server', 'connection refused',
                        'network is unreachable', 'could not connect to database')),
        ('filesystem', ('no such file or directory', 'permission denied', 'no space left on device')),
    ):
        if any(fragment in message for fragment in fragments):
            return category
    return 'unclassified'


def require(condition, message):
    if not condition:
        raise Stop(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(value, key):
    return hmac.new(key, json.dumps(value, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def process(command, env=None, *, tool_name='native_cluster', version=False, stdin=None, cwd=None):
    # Private, auto-closed temporary stderr; read at most 64 KiB, upload nothing.
    with tempfile.TemporaryFile() as errors:
        try:
            result = subprocess.run(command, env={**(env or {}), 'LC_ALL': 'C'}, stdin=stdin, cwd=cwd,
                                    stdout=subprocess.PIPE if version else subprocess.DEVNULL,
                                    stderr=errors, timeout=900)
        except subprocess.TimeoutExpired:
            raise ToolFailure(tool_name, None, 'timeout') from None
        except FileNotFoundError:
            raise ToolFailure(tool_name, None, 'executable_unavailable') from None
        except OSError:
            raise ToolFailure(tool_name, None, 'process_start_failed') from None
        if result.returncode:
            errors.seek(0)
            stderr = errors.read(65536).decode('utf-8', errors='replace')
            # The isolated helper emits only structured, allowlisted diagnostics.
            try:
                detail = json.loads(stderr)
                if isinstance(detail, dict) and set(detail) == {'tool', 'exit_status', 'category'}:
                    raise ToolFailure(detail['tool'], detail['exit_status'], detail['category'])
            except (ValueError, TypeError):
                pass
            category = tool_error_category(stderr)
            raise ToolFailure(tool_name, result.returncode, category)
        return result.stdout if version else None


def tool(command, pg_env, *, version=False):
    require(command[0] in ('pg_dump', 'pg_restore'), 'Unexpected PostgreSQL executable.')
    return process(['/usr/lib/postgresql/18/bin/' + command[0], *command[1:]],
                   env={'PATH': '/usr/bin:/bin', **pg_env}, tool_name=command[0], version=version)


def verify_postgres_clients():
    expected = '18'
    for name in ('pg_dump', 'pg_restore'):
        output = tool([name, '--version'], {}, version=True)
        match = re.match(rb'^' + name.encode() + rb' \(PostgreSQL\) ([0-9]+)(?:\.[0-9]+)*\b', output)
        if not match:
            raise ToolFailure(name, 0, 'version_unrecognized')
        major = match[1].decode('ascii')
        if major != expected:
            raise ToolFailure(name, 0, 'version_mismatch')
        print(json.dumps({'postgres_tool': name, 'client_major': int(major)}), flush=True)


def native_cluster(action, receipt=None, stdin=None):
    require(action in ('create', 'stop', 'restore', 'fixture', 'fixture-dump', 'fixture-check'),
            'Unexpected isolated cluster action.')
    arguments = []
    if action != 'create':
        require(isinstance(receipt, dict) and set(receipt) == {'directory', 'cluster_id'}
                and isinstance(receipt['directory'], str)
                and re.fullmatch(r'/tmp/dawana-schema-restore-[a-f0-9]{32}', receipt['directory'])
                and isinstance(receipt['cluster_id'], str) and receipt['cluster_id'].isascii()
                and receipt['cluster_id'].isdecimal(), 'Invalid isolated cluster receipt.')
        arguments = [receipt['directory'], receipt['cluster_id']]
    # Neither sudo nor the database server receives the production environment.
    return process(['/usr/bin/sudo', '-n', '-u', 'dawana_restore', '/usr/bin/env', '-i',
                    'PATH=/usr/bin:/bin', 'LC_ALL=C', '/usr/bin/python3', '-I', '-B',
                    '/opt/dawana-schema-recovery/schema_recovery_native.py',
                    action, *arguments], env={'PATH': '/usr/bin:/bin'}, stdin=stdin, version=True, cwd='/tmp')


def restore_receipt_path():
    return Path(os.environ['RUNNER_TEMP']) / 'schema-recovery-restore.json'


def manage_isolated_cluster(create):
    path = restore_receipt_path()
    if create:
        require(not path.exists(), 'Isolated cluster receipt already exists; reuse refused.')
        receipt = json.loads(native_cluster('create'))
        try:
            with path.open('x', encoding='utf-8') as output:
                os.chmod(path, 0o600)
                json.dump(receipt, output)
        except BaseException:
            native_cluster('stop', receipt)
            raise
    elif path.exists():
        native_cluster('stop', json.loads(path.read_text()))
        path.unlink()


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


def restore_backup(archive, roles, receipt=None):
    """Stream only archive/NOLOGIN role names to the isolated OS account."""
    receipt = receipt if receipt is not None else json.loads(restore_receipt_path().read_text())
    with tempfile.TemporaryFile() as incoming, archive.open('rb') as source:
        incoming.write(json.dumps(roles).encode('utf-8') + b'\n')
        shutil.copyfileobj(source, incoming)
        incoming.seek(0)
        result = json.loads(native_cluster('restore', receipt, stdin=incoming))
    require(result == {'restore_verified': True}, 'Isolated restore verification failed.')


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
    os.umask(0o077)
    phase = os.environ['PHASE']
    require(phase in ('PREFLIGHT', 'INITIALIZE') and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'Manual dispatch required.')
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Automatic reruns forbidden.')
    require(os.environ.get('RECOVERY_POSTGRES_MAJOR') == '18',
            'This native recovery requires verified PostgreSQL major 18.')
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
    STAGE = 'PostgreSQL client validation'
    verify_postgres_clients()
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
            pg_env = dict(PGHOST=config['HOST'], PGPORT=str(config['PORT'] or '5432'),
                          PGDATABASE=config['NAME'], PGUSER=config['USER'],
                          PGPASSWORD=config['PASSWORD'], PGSSLMODE='verify-full',
                          PGSSLROOTCERT=config['OPTIONS']['sslrootcert'],
                          PGCHANNELBINDING=config['OPTIONS'].get('channel_binding', 'prefer'),
                          PGOPTIONS='-c default_transaction_read_only=on',
                          PGCONNECT_TIMEOUT='5')
            STAGE = 'read-only full production backup'
            tool(['pg_dump', '--format=custom', '--snapshot=' + snapshot,
                  '--file=' + str(archive)], pg_env)
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
        if sys.argv[1:] == ['--create-isolated-cluster']:
            manage_isolated_cluster(create=True)
        elif sys.argv[1:] == ['--stop-isolated-cluster']:
            manage_isolated_cluster(create=False)
        else:
            require(not sys.argv[1:], 'Unexpected recovery arguments.')
            run()
    except Exception as exc:
        cause = exc
        while cause.__cause__ is not None:
            cause = cause.__cause__
        state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        state = state if isinstance(state, str) and re.fullmatch('[0-9A-Z]{5}', state) else None
        report = {'recovery': 'STOP', 'stage': STAGE, 'reason': str(exc) if isinstance(exc, Stop)
                  else 'Operation failed; no automatic retry.', 'sqlstate': state}
        if isinstance(exc, ToolFailure):
            report.update(exc.diagnostic)
        print(json.dumps(report), flush=True)
        sys.exit(1)
