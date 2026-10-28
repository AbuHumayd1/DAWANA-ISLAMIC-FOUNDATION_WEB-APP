"""Step B: preflight/archive reads only. No backup, restore, DDL or application imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / 'output/acceptance/migration-verification-2c9499d80e584c1ca72fc04efe0d68b9.json'
RECEIPT_SHA256 = 'c70fa32d1de80e6e426a2f90d8a030548cdf5bdd96c8063a822a076b05e27d9f'
DATABASE = 'dic_2026_demo'
PRIVATE = ROOT / '.local-preview'
TOOLS = ('pg_dump', 'pg_restore', 'psql')


class ReadinessError(Exception):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse otherwise echoes unknown arguments, which may contain credentials.
        self.exit(2, 'FAIL: Invalid readiness arguments; values suppressed. Use --help.\n')


def require(condition, message):
    if not condition:
        raise ReadinessError(message)


def redact(value, secrets=()):
    text = re.sub(r'(?i)postgres(?:ql)?://\S+', '[redacted URL]', str(value))
    text = re.sub(r'(?i)(password\s*[=:]\s*)("[^"]*"|\x27[^\x27]*\x27|\S+)', r'\1[redacted]', text)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    return text


def target_guard(database, host, port, username):
    require(database == DATABASE, 'Only the explicitly designated dic_2026_demo database is allowed.')
    # Numeric loopback prevents DNS, socket, multi-host and service indirection.
    require(host == '127.0.0.1' and str(port) == '5432', 'Target must match the pinned receipt: 127.0.0.1:5432.')
    require(bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', username or '')), 'Supply an explicit simple PostgreSQL role name.')


def restore_guard(name):
    require(bool(re.fullmatch(r'dic_2026_restore_[a-f0-9]{12,32}', name or '')),
            'Restore requires a separately approved disposable name: dic_2026_restore_<12-32 lowercase hex>.')


def destination_guard(destination):
    path = Path(destination)
    require(path.is_absolute(), 'Backup destination must be an absolute local path.')
    path = path.resolve()
    require(PRIVATE.resolve() == PRIVATE.absolute(), 'Private backup root must not redirect through a symlink/junction.')
    require(PRIVATE.resolve() in path.parents, 'Backup destination must be inside the ignored .local-preview directory.')
    # Reject symlinks/junctions resolving out of the private root; never mkdir or probe-write.
    require(path.suffix == '.dump' and not path.exists(), 'Destination must be a new, nonexistent .dump file; never overwrite.')
    require(path.parent.is_dir(), 'Backup parent directory must already exist; create/restrict it separately.')
    require(os.access(path.parent, os.W_OK), 'Backup parent is not writable (no probe file was created).')
    free = shutil.disk_usage(path.parent).free
    return path, free


def find_tools(explicit=None, bin_dir=None):
    explicit = explicit or {}
    candidates = []
    if bin_dir:
        require(Path(bin_dir).is_absolute(), 'PgBin must be an absolute directory.')
        candidates.append(Path(bin_dir))
    elif explicit:
        candidates.append(Path(next(iter(explicit.values()))).parent)
    else:
        base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PostgreSQL'
        if base.is_dir():
            candidates.extend(p / 'bin' for p in sorted(base.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1, reverse=True) if p.name.isdigit())
        located = shutil.which('psql')
        if located:
            candidates.append(Path(located).parent)
    suffix = '.exe' if os.name == 'nt' else ''
    for folder in candidates:
        paths = {name: Path(explicit.get(name, folder / (name + suffix))) for name in TOOLS}
        require(all(p.is_absolute() for p in paths.values()), 'Executable paths must be absolute.')
        if all(p.is_file() for p in paths.values()):
            return {k: str(v.resolve()) for k, v in paths.items()}
        if bin_dir or explicit:
            break  # Invalid explicit configuration must never silently fall back.
    raise ReadinessError('PostgreSQL tooling missing/incomplete. Configure PgBin or all explicit executable paths; nothing installed.')


def child_environment(password_env=None, passfile=None):
    require(not (password_env and passfile), 'Choose one explicit credential source.')
    child = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')
             and not any(s in k.upper() for s in ('PASSWORD', 'SECRET', 'TOKEN', 'DATABASE_URL', 'ACCESS_KEY'))}
    child.update(PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000',
                 PGCONNECT_TIMEOUT='5', PGAPPNAME='dic-step-b-readiness', PGSSLMODE='disable',
                 PGPASSFILE=str(PRIVATE / 'credential-discovery-disabled.pgpass'))
    # A sentinel must not exist: disable implicit ~/.pgpass lookup without creating a file.
    require(not Path(child['PGPASSFILE']).exists(), 'Credential sentinel exists; remove implicit credential ambiguity separately.')
    if password_env:
        require(bool(re.fullmatch(r'[A-Z_][A-Z0-9_]*', password_env)), 'Invalid password environment variable name.')
        require(bool(os.environ.get(password_env)), 'Configured password environment variable is empty/missing.')
        child['PGPASSWORD'] = os.environ[password_env]
    if passfile:
        require(Path(passfile).is_absolute() and Path(passfile).is_file(), 'Passfile must be an explicit existing absolute file.')
        child['PGPASSFILE'] = str(Path(passfile).resolve())
    return child


def run_read(command, env, runner=subprocess.run):
    """Allowlist every invocation; even future callers cannot invoke dump/restore writes."""
    name = Path(command[0]).stem
    args = command[1:]
    allowed = args == ['--version'] and name in TOOLS
    allowed |= name == 'psql' and args == connection_args(env.get('DIC_READINESS_USER', ''))
    allowed |= name == 'pg_restore' and (len(args) == 2 and args[0] == '--list'
        or len(args) == 3 and args[:2] == ['--file', os.devnull])
    require(allowed, 'Invocation rejected: workflow supports version, fixed read-only SELECT and offline archive reads only.')
    if name == 'psql' and args != ['--version']:
        require(env.get('PGOPTIONS') == '-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000'
                and not any(k in env for k in ('PGHOST', 'PGHOSTADDR', 'PGSERVICE', 'PGDATABASE', 'PGPORT')),
                'Read-only connection environment guard failed.')
    try:
        result = runner(command, env={k: v for k, v in env.items() if k != 'DIC_READINESS_USER'},
                        capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ReadinessError('PostgreSQL tool could not start or timed out; no raw diagnostic retained.') from None
    require(result.returncode == 0, 'PostgreSQL tool failed; raw stdout/stderr suppressed to protect credentials/data.')
    return result.stdout


SQL = """SELECT current_database(), inet_server_addr()::text, inet_server_port(),
current_setting('transaction_read_only'), current_setting('server_version_num'), current_user,
pg_database_size(current_database()),
(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'
 AND c.relkind IN ('r','p','m','v','f') AND NOT has_table_privilege(current_user,c.oid,'SELECT')),
(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'
 AND c.relkind='S' AND NOT has_sequence_privilege(current_user,c.oid,'SELECT')),
(SELECT count(*) FROM pg_class WHERE relrowsecurity),
(SELECT count(*) FROM pg_largeobject_metadata WHERE NOT has_largeobject_privilege(current_user,oid,'SELECT'));
"""


def connection_args(username):
    return ['--no-psqlrc', '--no-password', '--host', '127.0.0.1', '--port', '5432',
            '--username', username, '--dbname', DATABASE, '--set', 'ON_ERROR_STOP=1',
            '--tuples-only', '--no-align', '--command', SQL]


def versions(tools, env):
    result = {}
    for name, path in tools.items():
        output = run_read([path, '--version'], env)
        match = re.fullmatch(r'\s*' + name + r' \(PostgreSQL\) (\d+)(?:\.(\d+))?[^\r\n]*\s*', output)
        require(match is not None, 'Unrecognized PostgreSQL version output; raw output suppressed.')
        result[name] = (int(match[1]), int(match[2] or 0))
    require(len(set(result.values())) == 1, 'Tool versions differ; supply a matching trusted PostgreSQL toolset.')
    return result


def verify_connection(tools, env, username, major, free):
    env = dict(env, DIC_READINESS_USER=username)
    fields = run_read([tools['psql'], *connection_args(username)], env).strip().split('|')
    require(len(fields) == 11, 'Unexpected identity response; raw response suppressed.')
    database, host, port, readonly, server, role, size, tables, sequences, rls, largeobjects = fields
    require((database, host, port, readonly, role) == (DATABASE, '127.0.0.1', '5432', 'on', username), 'Connected database/endpoint/role/read-only identity mismatch.')
    require(server.isdigit() and int(server) // 10000 == major, 'Server/tool major version mismatch; select the matching PgBin explicitly.')
    require(size.isdigit() and free >= max(1024**3, int(size) * 2), 'Insufficient conservative backup headroom (2x database size, minimum 1 GiB).')
    require(all(v == '0' for v in (tables, sequences, rls, largeobjects)),
            'Backup privilege/RLS prerequisite blocked: missing SELECT rights or row-security tables need separate review; no grants performed.')
    return dict(database=database, host=host, port=port, transaction_read_only=True, server_major=major,
                database_size_bytes=int(size), disk_free_bytes=free, select_privilege_gaps=0,
                row_security_tables=0, backup_privileges_fully_proven=False)


def receipt_check(path=RECEIPT):
    content = Path(path).read_bytes()
    require(hashlib.sha256(content).hexdigest() == RECEIPT_SHA256, 'Pinned migration receipt checksum changed; preserve the approved evidence.')
    value = json.loads(content)
    require(value['identity'] == dict(database=DATABASE, host='127.0.0.1', port='5432', transaction_read_only=True)
            and value['database_writes'] is False and len(value['applied']) == 44 and len(value['pending']) == 11,
            'Pinned migration receipt identity/counts mismatch.')
    for step in value['manifest']['steps']:
        app, name = step['app'], step['name']
        require(re.fullmatch(r'[a-z_]+', app) and re.fullmatch(r'[a-z0-9_]+', name), 'Invalid migration receipt source path.')
        source = ROOT / 'backend' / app / 'migrations' / (name + '.py')
        # Django's own migrations live in the environment, not repository source.
        if source.is_file():
            require(hashlib.sha256(source.read_bytes()).hexdigest() == step['source_sha256'], 'Migration source differs from the pinned receipt; re-review required.')
    return hashlib.sha256(content).hexdigest()


def verify_archive(tools, env, archive, expected):
    path = Path(archive).resolve()
    require(PRIVATE.resolve() in path.parents and path.is_file(), 'Archive must be an existing private local file.')
    require(bool(re.fullmatch(r'[a-f0-9]{64}', expected or '')), 'Supply the separately recorded SHA-256 for this archive.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        require(stream.read(5) == b'PGDMP', 'Not a custom-format PostgreSQL archive.')
        stream.seek(0)
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    require(digest.hexdigest() == expected, 'Archive checksum mismatch.')
    listing = run_read([tools['pg_restore'], '--list', str(path)], env)
    require(re.search(r'^;\s+dbname:\s*dic_2026_demo\s*$', listing, re.M) is not None,
            'Archive source database does not match dic_2026_demo.')
    require(re.search(r'^\d+;\s', listing, re.M) is not None, 'Archive contains no TOC entries.')
    run_read([tools['pg_restore'], '--file', os.devnull, str(path)], env)
    return dict(sha256=expected, size_bytes=path.stat().st_size, toc_and_full_read=True, restore_rehearsed=False)


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', default=DATABASE)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default='5432')
    parser.add_argument('--username', default=os.environ.get('DIC_DEMO_PG_USER', ''))
    parser.add_argument('--pg-bin', default=os.environ.get('DIC_PG_BIN'))
    for tool in TOOLS:
        parser.add_argument('--' + tool.replace('_', '-') + '-path', default=os.environ.get('DIC_' + tool.upper() + '_PATH'))
    parser.add_argument('--destination', default=str(PRIVATE / 'dic_2026_demo_step_b.dump'))
    parser.add_argument('--password-env')
    parser.add_argument('--passfile')
    parser.add_argument('--check-connection', action='store_true', help='One fixed read-only identity/size SELECT against the pinned demo endpoint.')
    parser.add_argument('--restore-database', help='Validate a disposable name only; never connect/create/restore.')
    parser.add_argument('--archive', help='Existing archive for offline verification; never created here.')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    try:
        target_guard(args.database, args.host, args.port, args.username)
        if args.restore_database:
            restore_guard(args.restore_database)
        receipt_hash = receipt_check()
        destination, free = destination_guard(args.destination)
        explicit = {name: getattr(args, name + '_path') for name in TOOLS if getattr(args, name + '_path')}
        tools = find_tools(explicit, args.pg_bin)
        env = child_environment(args.password_env, args.passfile)
        tool_versions = versions(tools, env)
        print('PASS: target guards, preserved receipt, new private destination and matching tool versions.')
        print(json.dumps(dict(mode='preflight-only', database=DATABASE, endpoint='127.0.0.1:5432',
            tools=tools, versions=tool_versions, migration_receipt_sha256=receipt_hash,
            destination=str(destination), disk_free_bytes=free, database_writes=False, backup_created=False)))
        if args.check_connection:
            print('PASS: read-only connected identity: ' + json.dumps(verify_connection(tools, env, args.username, tool_versions['psql'][0], free)))
        else:
            print('NOT RUN: server identity/version, backup privilege and size/headroom verification (use --check-connection).')
        if args.archive:
            print('PASS: offline archive integrity: ' + json.dumps(verify_archive(tools, env, args.archive, args.expected_sha256)))
        else:
            print('NOT RUN: archive integrity; no backup created.')
        print('NOT RUN: real backup, disposable provisioning, restore rehearsal, migrations and production access. Separate approvals required.')
        return 0
    except ReadinessError as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError):
        # Never echo untrusted config, exception text or tool diagnostics.
        print('FAIL: Step B readiness blocked. Check target, receipt, private destination, tools, credentials and version prerequisites. No backup/restore performed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
