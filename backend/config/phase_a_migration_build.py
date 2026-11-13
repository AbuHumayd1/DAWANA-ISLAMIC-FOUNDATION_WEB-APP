"""One-time Render build operation. Never imported by web/build/start commands.

Uses the release_migrations approval/identity contract, with a narrower executor:
only 0041, no post_migrate hooks, and one PostgreSQL transaction/try-lock.
"""
import base64
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys

from config.release_migrations import plan_manifest, validate_approval, validate_target

TARGET = ('dic', '0041_phase_a_order_lifecycle')
PREFIX = '[phase-a-migration] '


class Stop(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Stop(code)


def inputs(env):
    require(env.get('RENDER') == 'true', 'RENDER_REQUIRED')
    mode = env.get('DAWANA_PHASE_A_MODE')
    require(mode in ('plan', 'apply'), 'EXPLICIT_MODE_REQUIRED')
    commit = env.get('RENDER_GIT_COMMIT', '')
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'RELEASE_COMMIT_REQUIRED')
    expected = {}
    for field in ('database', 'host', 'port', 'role', 'cluster_id'):
        value = env.get('DAWANA_PHASE_A_' + field.upper(), '')
        require(value and value == value.strip() and not any(c in value for c in '\r\n\0'),
                'EXPLICIT_IDENTITY_REQUIRED')
        expected[field] = value
    require(expected['database'] not in ('dawana_dev', 'dic_2026_demo', 'postgres', 'template0', 'template1'),
            'PRODUCTION_DATABASE_REQUIRED')
    require(re.fullmatch(r'[0-9]+', expected['cluster_id']) and expected['cluster_id'] != '0',
            'CLUSTER_ID_REQUIRED')
    require(expected['port'].isdigit() and 0 < int(expected['port']) < 65536, 'PORT_INVALID')
    approval = None
    if mode == 'apply':
        try:
            raw = base64.b64decode(env.get('DAWANA_PHASE_A_APPROVAL_B64', ''), validate=True)
            require(len(raw) <= 65536, 'APPROVAL_INVALID')
            require(hashlib.sha256(raw).hexdigest() == env.get('DAWANA_PHASE_A_APPROVAL_SHA256'),
                    'APPROVAL_DIGEST_MISMATCH')
            approval = json.loads(raw)
            require(isinstance(approval, dict) and approval.get('release_commit') == commit,
                    'APPROVAL_RELEASE_MISMATCH')
        except (ValueError, TypeError):
            raise Stop('APPROVAL_INVALID') from None
    return mode, expected, commit, approval


def check_config(config, expected):
    require(config.get('ENGINE') == 'django.db.backends.postgresql', 'POSTGRES_REQUIRED')
    require(config.get('NAME') == expected['database'], 'DATABASE_MISMATCH')
    options = config.get('OPTIONS', {})
    require(options.get('sslmode') == 'verify-full', 'VERIFY_FULL_REQUIRED')
    root = options.get('sslrootcert')
    require(root and Path(root).is_file() and os.access(root, os.R_OK), 'TRUSTED_CA_REQUIRED')
    # Do not permit libpq service/alternate endpoint overrides.
    require(not any(key in options for key in ('service', 'servicefile', 'host', 'hostaddr',
                                               'port', 'dbname', 'user', 'sslcertmode')),
            'CONNECTION_OVERRIDE_REJECTED')
    require('.' in expected['host'] and ',' not in expected['host'], 'EXTERNAL_TLS_HOST_REQUIRED')
    try:
        validate_target(config, expected, expected)
    except RuntimeError:
        raise Stop('ENDPOINT_MISMATCH') from None


def exact_plan(executor):
    loader = executor.loader
    loader.check_consistent_history(executor.connection)
    require(not loader.detect_conflicts(), 'GRAPH_CONFLICT')
    require(TARGET in loader.graph.nodes, 'TARGET_MISSING')
    plan = executor.migration_plan(loader.graph.leaf_nodes())
    require(bool(plan), 'NO_PENDING_MIGRATIONS_VERIFY_PRIOR_ATTEMPT')
    require(len(plan) == 1 and not plan[0][1]
            and (plan[0][0].app_label, plan[0][0].name) == TARGET,
            'UNEXPECTED_PENDING_PLAN')
    migration = plan[0][0]
    # RC3 is additive schema only. Never run an unexpected data/custom operation.
    from django.db.migrations.operations.models import CreateModel
    require(migration.atomic and len(migration.operations) == 3
            and all(type(op) is CreateModel for op in migration.operations)
            and {op.name for op in migration.operations} == {'OrderExpiry', 'OrderExpiryPolicy', 'PaymentResolution'},
            'TARGET_OPERATIONS_CHANGED')
    return plan


def execute(connection, transaction, executor_factory, mode, expected, commit, approval):
    require(mode in ('plan', 'apply'), 'EXPLICIT_MODE_REQUIRED')
    if mode == 'apply':
        require(isinstance(approval, dict) and approval.get('release_commit') == commit,
                'APPROVAL_RELEASE_MISMATCH')
    check_config(connection.settings_dict, expected)
    with transaction.atomic(using='default'):
        with connection.cursor() as cursor:
            if mode == 'plan':
                cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute('SELECT pg_try_advisory_xact_lock(17428041, 41)')
            require(cursor.fetchone()[0] is True, 'MIGRATION_LOCK_BUSY')
            cursor.execute('SELECT current_database(), current_user, system_identifier::text '
                           'FROM pg_control_system()')
            actual = dict(zip(('database', 'role', 'cluster_id'), cursor.fetchone()))
            try:
                validate_target(connection.settings_dict, expected, actual)
            except RuntimeError:
                raise Stop('CONNECTED_IDENTITY_MISMATCH') from None
            cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
            require(cursor.fetchone() == (True,), 'TLS_SESSION_REQUIRED')
        executor = executor_factory(connection)
        plan = exact_plan(executor)
        manifest = plan_manifest(executor.loader, plan, expected['database'],
                                 'config.settings.render', {**expected, **actual})
        if mode == 'plan':
            return {'release_commit': commit, 'manifest': manifest}
        try:
            validate_approval(manifest, approval)
        except RuntimeError:
            raise Stop('APPROVAL_PLAN_MISMATCH') from None
        executor.migrate([TARGET], plan=plan)
        refreshed = executor_factory(connection)
        require(not refreshed.migration_plan(refreshed.loader.graph.leaf_nodes())
                and TARGET in refreshed.loader.applied_migrations, 'SCHEMA_STILL_PENDING')
        # No post_migrate signals: they can create unrelated permissions/seed data.
        # MigrationRecorder and 0041's DDL are the only authorized writes here.
    return None  # transaction has committed before success is reported


def main():
    # Emit only fixed error codes. Settings/driver exceptions may contain credentials.
    logging.disable(logging.CRITICAL)
    try:
        mode, expected, commit, approval = inputs(os.environ)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import django
            django.setup()
            from django.db import connection, transaction
            from django.db.migrations.executor import MigrationExecutor
            try:
                result = execute(connection, transaction, MigrationExecutor,
                                 mode, expected, commit, approval)
            finally:
                connection.close()
        if mode == 'plan':
            print(PREFIX + 'PLAN: read-only; no migrations applied.')
            print(json.dumps(result, sort_keys=True))
        else:
            print(PREFIX + 'APPLIED: dic.0041_phase_a_order_lifecycle committed; no pending migrations.')
        return 0
    except Exception as exc:
        print(PREFIX + 'STOP: ' + (str(exc) if type(exc) is Stop else 'INTERNAL_FAILURE_REVIEW_PRIVATELY'),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
