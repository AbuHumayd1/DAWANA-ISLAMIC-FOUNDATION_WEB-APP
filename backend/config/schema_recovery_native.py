"""Disposable PG18 restore worker. Runs only as the dedicated unprivileged account.

No Django, dotenv, production connection settings, passwords, or remote targets.
Only a receipt-bound private Unix socket can be used for SQL and restoration.
"""
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_schema_recovery import Stop, ToolFailure, process, require

BIN = Path('/usr/lib/postgresql/18/bin')
OWNER = 'dawana_restore'
DATABASE = 'recovery_restore'
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'PGCONNECT_TIMEOUT': '5',
       'PGCLIENTENCODING': 'UTF8', 'PGOPTIONS': '-c search_path=pg_catalog'}


def dedicated_account():
    require(os.geteuid() != 0 and os.geteuid() == pwd.getpwnam(OWNER).pw_uid,
            'Dedicated restore account required.')
    # Defense in depth: the wrapper must already have removed the environment.
    require(set(os.environ) <= {'PATH', 'LC_ALL', 'LC_CTYPE'}, 'Unexpected restore environment.')


def directory_guard(value):
    require(isinstance(value, str) and re.fullmatch(r'/tmp/dawana-schema-restore-[a-f0-9]{32}', value),
            'Invalid isolated directory.')
    root = Path(value)
    info = root.lstat()
    require(root.resolve() == root and stat.S_ISDIR(info.st_mode)
            and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
            'Unsafe isolated directory.')
    return root


def pg(name, arguments, *, stdin=None, capture=False):
    require(name in ('initdb', 'pg_ctl', 'psql', 'pg_dump', 'pg_restore'), 'Unexpected native tool.')
    return process([str(BIN / name), *arguments], ENV, tool_name=name, stdin=stdin, version=capture)


def connection_args(root, database=DATABASE):
    require(database in (DATABASE, 'postgres'), 'Unexpected isolated database.')
    return ['--host=' + str(root / 'socket'), '--port=5432', '--username=' + OWNER,
            '--dbname=' + database, '--no-password']


def sql(root, statement, *, database=DATABASE, capture=False):
    with tempfile.TemporaryFile() as incoming:
        incoming.write(statement.encode('utf-8'))
        incoming.seek(0)
        return pg('psql', [*connection_args(root, database), '--no-psqlrc', '--set=ON_ERROR_STOP=1',
                          '--tuples-only', '--no-align'], stdin=incoming, capture=capture)


def identity(root):
    for path in (root / 'data', root / 'socket'):
        info = path.lstat()
        require(path.resolve() == path and stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'Unsafe isolated cluster permissions.')
    result = json.loads(sql(root, """
        SELECT json_build_object('database', current_database(), 'role', current_user,
            'data', current_setting('data_directory'), 'listen', current_setting('listen_addresses'),
            'socket', current_setting('unix_socket_directories'), 'port', current_setting('port'),
            'major', current_setting('server_version_num')::integer / 10000,
            'cluster_id', system_identifier::text) FROM pg_control_system();
    """, capture=True))
    expected = dict(database=DATABASE, role=OWNER, data=str(root / 'data'), listen='',
                    socket=str(root / 'socket'), port='5432', major=18, cluster_id=result.get('cluster_id'))
    require(result == expected and isinstance(result['cluster_id'], str)
            and re.fullmatch(r'[0-9]+', result['cluster_id']), 'Isolated cluster identity mismatch.')
    return result['cluster_id']


def verify(root, cluster_id, *, live=True):
    marker = root / 'receipt.json'
    info = marker.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600, 'Unsafe isolated receipt.')
    require(json.loads(marker.read_text()) == {'cluster_id': cluster_id}, 'Isolated receipt mismatch.')
    if live:
        require(identity(root) == cluster_id, 'Isolated server identity mismatch.')


def cleanup(root):
    directory_guard(str(root))
    if (root / 'data/postmaster.pid').exists():
        pg('pg_ctl', ['-D', str(root / 'data'), '-w', '-t', '60', '-m', 'immediate', 'stop'])
    # Only the exact owned, private, freshly generated root passes the guard.
    shutil.rmtree(root)


def create():
    root = Path('/tmp/dawana-schema-restore-' + uuid.uuid4().hex)
    root.mkdir(mode=0o700)
    try:
        (root / 'socket').mkdir(mode=0o700)
        pg('initdb', ['-D', str(root / 'data'), '--username=' + OWNER, '--encoding=UTF8',
                      '--locale=C', '--auth-local=peer', '--auth-host=reject', '--no-instructions'])
        pg('pg_ctl', ['-D', str(root / 'data'), '-l', str(root / 'server.log'), '-w', '-t', '60',
                      '-o', "-c listen_addresses='' -c unix_socket_directories='" + str(root / 'socket')
                      + "' -c unix_socket_permissions=0700 -c port=5432 -c log_statement=none"
                      + ' -c log_min_error_statement=panic', 'start'])
        sql(root, 'CREATE DATABASE recovery_restore TEMPLATE template0;', database='postgres')
        cluster_id = identity(root)
        with (root / 'receipt.json').open('x') as marker:
            json.dump({'cluster_id': cluster_id}, marker)
        return dict(directory=str(root), cluster_id=cluster_id)
    except BaseException:
        cleanup(root)
        raise


def restore(root, cluster_id, incoming):
    # Verify the actual server BEFORE CREATE ROLE, pg_restore --clean, or any SQL write.
    verify(root, cluster_id)
    header = incoming.readline(2 * 1024 * 1024)
    require(header.endswith(b'\n'), 'Invalid isolated role header.')
    roles = json.loads(header)
    require(isinstance(roles, list) and all(isinstance(role, str) and '\0' not in role for role in roles),
            'Invalid isolated roles.')
    existing = json.loads(sql(root, "SELECT COALESCE(json_agg(rolname), '[]') FROM pg_roles;", capture=True))
    for role in roles:
        if role not in existing:
            sql(root, 'CREATE ROLE "' + role.replace('"', '""') + '" NOLOGIN;')
            existing.append(role)
    archive = root / 'restore.dump'
    created = False
    try:
        with archive.open('xb') as output:
            created = True
            shutil.copyfileobj(incoming, output)
        require(archive.stat().st_size > 0, 'Empty isolated archive.')
        pg('pg_restore', [*connection_args(root), '--clean', '--if-exists', '--exit-on-error',
                          '--single-transaction', str(archive)])
        verify(root, cluster_id)
        return {'restore_verified': True}
    finally:
        if created:
            archive.unlink()


def fixture(root, cluster_id, action):
    """Fixed SYNTHETIC data only, usable exclusively in a verified private cluster."""
    verify(root, cluster_id)
    if action == 'fixture':
        sql(root, """
            CREATE ROLE recovery_test_owner NOLOGIN;
            CREATE ROLE recovery_test_reader NOLOGIN;
            CREATE SCHEMA recovery_test AUTHORIZATION recovery_test_owner;
            CREATE TABLE recovery_test.items (id integer PRIMARY KEY, label text);
            ALTER TABLE recovery_test.items OWNER TO recovery_test_owner;
            INSERT INTO recovery_test.items VALUES (1, 'synthetic one'), (2, 'synthetic two');
            GRANT USAGE ON SCHEMA recovery_test TO recovery_test_reader;
            GRANT SELECT ON recovery_test.items TO recovery_test_reader;
        """)
        return {'fixture': True}
    if action == 'fixture-check':
        result = json.loads(sql(root, """
            SELECT json_build_object('rows', (SELECT count(*) FROM recovery_test.items),
                'owner', (SELECT tableowner FROM pg_tables WHERE schemaname='recovery_test' AND tablename='items'),
                'select', has_table_privilege('recovery_test_reader','recovery_test.items','SELECT'),
                'insert', has_table_privilege('recovery_test_reader','recovery_test.items','INSERT'),
                'nologin', NOT (SELECT rolcanlogin FROM pg_roles WHERE rolname='recovery_test_reader'));
        """, capture=True))
        require(result == dict(rows=2, owner='recovery_test_owner', select=True, insert=False, nologin=True),
                'Synthetic restore contents or ACL mismatch.')
        return {'fixture_verified': True}
    # No arbitrary database, SQL, path or credentials are accepted from the runner.
    path = root / 'synthetic.dump'
    try:
        pg('pg_dump', [*connection_args(root), '--format=custom', '--file=' + str(path)])
        with path.open('rb') as source:
            shutil.copyfileobj(source, sys.stdout.buffer)
    finally:
        path.unlink(missing_ok=True)
    return None


def main():
    os.umask(0o077)
    dedicated_account()
    require(len(sys.argv) in (2, 4), 'Invalid isolated action arguments.')
    action = sys.argv[1]
    if action == 'create':
        require(len(sys.argv) == 2, 'Invalid isolated create arguments.')
        result = create()
    else:
        require(len(sys.argv) == 4, 'Isolated receipt required.')
        root = directory_guard(sys.argv[2])
        cluster_id = sys.argv[3]
        require(bool(re.fullmatch(r'[0-9]+', cluster_id)), 'Invalid isolated cluster identity.')
        verify(root, cluster_id, live=action != 'stop')
        if action == 'stop':
            cleanup(root)
            result = {'stopped': True}
        elif action == 'restore':
            result = restore(root, cluster_id, sys.stdin.buffer)
        elif action in ('fixture', 'fixture-dump', 'fixture-check'):
            result = fixture(root, cluster_id, action)
        else:
            raise Stop('Unknown isolated action.')
    if result is not None:
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        detail = exc.diagnostic if isinstance(exc, ToolFailure) else dict(
            tool='native_cluster', exit_status=None, category='unclassified')
        print(json.dumps(detail), file=sys.stderr, flush=True)
        sys.exit(1)
