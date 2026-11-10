"""Read-only PostgreSQL 18 preview planning. No creation/migration/server actions."""
import argparse
from datetime import datetime, timezone
import getpass
from pathlib import Path
import socket
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dic_fee_postgres import connect, identity, database_info, require, save_new


def port_is_free(port):
    # Bind only for this check, without listening or starting a service.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    require(not args.plan.exists(), 'Plan already exists; choose a new path.')
    require(args.plan.parent.is_dir(), 'Plan parent directory must already exist.')
    data = dict(purpose='dic2026-local-visual-preview', host='127.0.0.1', port=5433,
        user=args.user, database='dawana_dic_preview_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        + '_' + uuid.uuid4().hex[:12], marker=uuid.uuid4().hex,
        backend_port=8001, frontend_port=5175, status='planned-only')
    password = getpass.getpass('Approved local PostgreSQL role password (not saved): ')
    with connect(data, password, readonly=True) as conn:
        require(conn.execute('SHOW transaction_read_only').fetchone() == ('on',),
                'Read-only preflight required.')
        data['identity'] = identity(conn)
        require(data['identity']['user'] == args.user, 'Role mismatch.')
        require(data['identity']['port'] == 5433, 'Server port must be 5433.')
        require(180000 <= int(data['identity']['version']) < 190000, 'PostgreSQL 18 required.')
        require(conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user')
                .fetchone() == (True,), 'Existing CREATEDB privilege required; no grants will be made.')
        require(database_info(conn, data['database']) is None, 'Generated database name already exists.')
        # Catalog inspection only; no connections to any listed database.
        data['protected_baseline'] = [dict(oid=row[0], name=row[1]) for row in
            conn.execute('SELECT oid::bigint, datname FROM pg_database ORDER BY oid')]
        data['baseline_oids'] = [row['oid'] for row in data['protected_baseline']]
        data['baseline_names'] = [row['name'] for row in data['protected_baseline']]
    require(port_is_free(8001), 'Port 8001 is occupied; leave its process untouched.')
    require(port_is_free(5175), 'Port 5175 is occupied; leave its process untouched.')
    save_new(args.plan, data)
    print('Read-only preflight passed; plan saved:', args.plan)
    print('Proposed NEW preview database:', data['database'])
    print('Cluster identity:', data['identity'])
    print('All existing database names/OIDs are protected by the baseline; OID 25041 is always forbidden.')
    print('No creation, migrations, seed writes or server launches performed.')


if __name__ == '__main__':
    main()
