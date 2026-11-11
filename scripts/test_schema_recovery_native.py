"""Production-free PG18 integration; only new private clusters under a dedicated UID.

Run on the ephemeral Ubuntu job AFTER packages/account/dependencies are installed
and BEFORE any production-secret-bearing step. No Django settings are imported.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('recovery_tools', ROOT / 'backend/config/github_schema_recovery.py')
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def main():
    recovery.require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true',
                     'Ephemeral Linux Actions job required for integration.')
    recovery.require(not any(os.environ.get(name) for name in
                     ('RECOVERY_DJANGO_ENV', 'RECOVERY_BACKUP_KEY', 'DATABASE_URL', 'PGPASSWORD')),
                     'Integration must precede production credentials.')
    os.umask(0o077)
    recovery.verify_postgres_clients()
    clusters = []
    try:
        for _ in range(2):
            clusters.append(json.loads(recovery.native_cluster('create')))
        source, target = clusters
        recovery.require(source['directory'] != target['directory'] and source['cluster_id'] != target['cluster_id'],
                         'Integration requires independent fresh clusters.')
        recovery.native_cluster('fixture', source)
        with tempfile.TemporaryDirectory(prefix='dawana-synthetic-archive-') as temporary:
            directory = Path(temporary)
            archive, encrypted, decrypted = [directory / name for name in ('synthetic.dump', 'synthetic.enc', 'restored.dump')]
            archive.write_bytes(recovery.native_cluster('fixture-dump', source))
            roles = ['dawana_restore', 'recovery_test_owner', 'recovery_test_reader']
            # Authenticate a real encrypted archive, then restore its decrypted bytes.
            key = bytes(range(32))  # Explicitly synthetic, never a production key.
            recovery.crypt_file(archive, encrypted, key)
            recovery.crypt_file(encrypted, decrypted, key, decrypt=True)
            recovery.require(recovery.digest(archive) == recovery.digest(decrypted), 'Synthetic encryption roundtrip failed.')
            from cryptography.exceptions import InvalidTag
            tampered = directory / 'tampered.enc'
            content = bytearray(encrypted.read_bytes())
            content[-1] ^= 1
            tampered.write_bytes(content)
            try:
                recovery.crypt_file(tampered, directory / 'rejected.dump', key, decrypt=True)
            except InvalidTag:
                pass
            else:
                raise recovery.Stop('Tampered encrypted archive was accepted.')
            try:
                recovery.restore_backup(decrypted, roles, {**target, 'cluster_id': '0'})
            except recovery.ToolFailure:
                pass
            else:
                raise recovery.Stop('Mismatched cluster identity was accepted.')
            broken = directory / 'broken.dump'
            broken.write_bytes(b'not a PostgreSQL archive')
            try:
                recovery.restore_backup(broken, roles, target)
            except recovery.ToolFailure:
                pass
            else:
                raise recovery.Stop('Invalid archive was accepted.')
            recovery.restore_backup(decrypted, roles, target)
            recovery.require(json.loads(recovery.native_cluster('fixture-check', target)) == {'fixture_verified': True},
                             'Synthetic contents/ownership/ACL verification failed.')
            # Also exercise --clean against the SAME disposable target, never production.
            recovery.restore_backup(decrypted, roles, target)
            recovery.native_cluster('fixture-check', target)
    finally:
        failures = []
        for receipt in reversed(clusters):
            try:
                recovery.native_cluster('stop', receipt)
            except Exception:
                failures.append(True)
        recovery.require(not failures, 'Synthetic cluster cleanup failed; no production operation allowed.')
    print('PASS: native PG18 dump/encryption/restore, tamper/wrong-identity/invalid-archive refusal, rows/ownership/ACLs and cleanup.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        report = dict(integration='STOP')
        if isinstance(exc, recovery.ToolFailure):
            report.update(exc.diagnostic)
        print(json.dumps(report), flush=True)  # Never print exception text or connection details.
        sys.exit(1)
