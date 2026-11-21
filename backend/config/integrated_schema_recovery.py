"""Exact 0042 recovery. Importing this module performs no database operations.

No management-command migrate, post_migrate, initialization or storage activation.
Production execution is exposed only by the deliberate failed-build wrapper.
"""
import base64
import contextlib
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import sys

from config.phase_a_migration_build import check_config
from config.release_migrations import digest, validate_approval, validate_target

TARGET = ('dic', '0042_integrated_camp_2026')
SOURCE_SHA256 = '3d94da0a3c5e2213fd01362686c72498d88cfc362f27e74cdef47612868648d0'
LOCK = (17428041, 42)


class Stop(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Stop(code)


def source_hash(migration):
    module = importlib.import_module(migration.__class__.__module__)
    return hashlib.sha256(Path(module.__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def environment(env, recovery=True):
    require(env.get('RENDER') == 'true', 'RENDER_REQUIRED')
    commit = env.get('RENDER_GIT_COMMIT', '')
    require(re.fullmatch('[0-9a-f]{40}', commit), 'RELEASE_COMMIT_REQUIRED')
    expected = {key: env.get('DAWANA_SCHEMA_' + key.upper(), '')
                for key in ('database', 'host', 'port', 'role', 'cluster_id')}
    require(all(value and value == value.strip() and not any(c in value for c in '\r\n\0')
                for value in expected.values()), 'EXPLICIT_IDENTITY_REQUIRED')
    require(expected['database'] not in ('postgres', 'template0', 'template1', 'dawana_dev', 'dic_2026_demo'),
            'PRODUCTION_DATABASE_REQUIRED')
    require(expected['cluster_id'].isdigit() and int(expected['cluster_id']) > 0, 'CLUSTER_ID_REQUIRED')
    require(expected['port'].isdigit() and 0 < int(expected['port']) < 65536, 'PORT_INVALID')
    mode = env.get('DAWANA_0042_MODE') if recovery else 'ready'
    require(mode in ('inspect', 'apply', 'verify', 'ready'), 'EXPLICIT_MODE_REQUIRED')
    require(not recovery or mode != 'ready', 'EXPLICIT_MODE_REQUIRED')
    approval = None
    if mode == 'apply':
        try:
            raw = base64.b64decode(env.get('DAWANA_0042_APPROVAL_B64', ''), validate=True)
            require(0 < len(raw) <= 65536, 'APPROVAL_INVALID')
            require(hashlib.sha256(raw).hexdigest() == env.get('DAWANA_0042_APPROVAL_SHA256'),
                    'APPROVAL_DIGEST_MISMATCH')
            approval = json.loads(raw)
            require(isinstance(approval, dict) and approval.get('release_commit') == commit,
                    'APPROVAL_RELEASE_MISMATCH')
        except (ValueError, TypeError):
            raise Stop('APPROVAL_INVALID') from None
    return mode, expected, commit, approval


def identity(connection, expected):
    # Reuse the established PostgreSQL/verify-full/CA/endpoint checks, without
    # changing or weakening the existing 0041 runner.
    try:
        check_config(connection.settings_dict, expected)
    except Exception:
        raise Stop('TLS_OR_CONFIGURED_IDENTITY_REJECTED') from None
    with connection.cursor() as cursor:
        try:
            cursor.execute('SELECT current_database(), current_user, system_identifier::text FROM pg_control_system()')
        except Exception:
            raise Stop('CONNECTED_CLUSTER_IDENTITY_UNAVAILABLE') from None
        actual = dict(zip(('database', 'role', 'cluster_id'), cursor.fetchone()))
        try:
            validate_target(connection.settings_dict, expected, actual)
        except RuntimeError:
            raise Stop('CONNECTED_IDENTITY_MISMATCH') from None
        cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
        require(cursor.fetchone() == (True,), 'TLS_SESSION_REQUIRED')
        cursor.execute('SHOW search_path')
        # Never resolve migration objects through an unexpected user schema.
        require(cursor.fetchone()[0] == 'public', 'EXPLICIT_PUBLIC_SCHEMA_REQUIRED')
    return {**expected, **actual}


def graph(executor, pinned=True):
    loader = executor.loader
    loader.check_consistent_history(executor.connection)
    require(not loader.detect_conflicts(), 'MIGRATION_GRAPH_CONFLICT')
    require(not (set(loader.applied_migrations) - set(loader.graph.nodes) - set(loader.replacements)),
            'UNKNOWN_RECORDED_MIGRATIONS')
    require(TARGET in loader.graph.nodes, 'TARGET_MISSING')
    # The historical, explicitly approved 0042 recovery MUST remain pinned to
    # 0042 even after later migrations are introduced. The release's normal
    # migration runner handles later migrations independently.
    full_plan = executor.migration_plan(loader.graph.leaf_nodes())
    require(not any(backwards for _, backwards in full_plan), 'BACKWARD_PLAN_REJECTED')
    # Exact approved additive successors are excluded from the 0042 recovery
    # operation itself. Reject any unrelated pending migration, changed
    # successor dependency, or backwards step rather than relaxing the guard.
    successors = (
        ('dic', '0043_exclude_dic2026_millionaire_drafts'),
        ('dic', '0044_studio_catalogue_placements'),
        ('dic', '0045_studio_hosted_video'),
        ('dic', '0046_aftercamp_assessments'),
        ('dic', '0047_studio_publications'),
        ('dic', '0048_studio_carousels'),
    )
    for previous, current in zip((TARGET,) + successors, successors):
        if current in loader.graph.nodes:
            require(previous in loader.graph.nodes[current].dependencies,
                    'UNRELATED_OR_MISSING_PENDING_PLAN')
    allowed = frozenset((TARGET,) + successors)
    require(all((m.app_label, m.name) in allowed for m, backwards in full_plan),
            'UNRELATED_OR_MISSING_PENDING_PLAN')
    # Django plans a reverse migration when the historical 0042 target is
    # requested after newer successors have already been applied. 0042 is
    # already present in that case: the recovery plan is empty, not a rollback.
    # The full leaf plan above still rejects real pending backwards steps.
    plan = [] if TARGET in loader.applied_migrations else executor.migration_plan([TARGET])
    require(not any(backwards for _, backwards in plan), 'BACKWARD_PLAN_REJECTED')
    target = loader.graph.nodes[TARGET]
    if pinned:
        from django.db.migrations.operations.models import CreateModel, AddConstraint
        from django.db.migrations.operations.fields import AddField, AlterField
        require(source_hash(target) == SOURCE_SHA256, 'TARGET_SOURCE_CHANGED')
        require(target.atomic and len(target.operations) == 23
                and all(type(op) in (CreateModel, AddField, AlterField, AddConstraint) for op in target.operations)
                and sum(type(op) is CreateModel for op in target.operations) == 3
                and sum(type(op) is AddConstraint for op in target.operations) == 3
                and ('dic', '0041_phase_a_order_lifecycle') in target.dependencies,
                'TARGET_OPERATIONS_CHANGED')
    return plan


def layout(loader):
    """Use historical models, never current ORM queries on the incompatible schema."""
    before = loader.project_state([('dic', '0041_phase_a_order_lifecycle')]).apps
    after = loader.project_state([TARGET]).apps
    result = {}
    for model in after.get_models():
        if model._meta.app_label != 'dic':
            continue
        try:
            old = before.get_model('dic', model._meta.model_name)
            old_cols = {f.column for f in old._meta.local_fields}
        except LookupError:
            old_cols = set()
        added = [f for f in model._meta.local_fields if f.column not in old_cols]
        if added:
            result[model._meta.db_table] = (model, added, not old_cols)
    return result


CONSTRAINTS = {
    'dic_house_canonical_unique': ('dic_house', ['edition_id', 'canonical_key'], True),
    'dic_food_date_meal_unique': ('dic_timetableentry', ['edition_id', 'date', 'meal'], True),
    'dic_certificate_person_unique': ('dic_participationcertificate', ['edition_id', 'participant_id'], False),
}


def expected_predicate(name, value):
    if name == 'dic_certificate_person_unique':
        return value is None
    normalized = re.sub(r'[\s()\"]', '', (value or '').replace('::text', ''))
    choices = {
        'dic_house_canonical_unique': {"NOTcanonical_key=''", "canonical_key<>''"},
        'dic_food_date_meal_unique': {"timetable_type='food'ANDNOTmeal=''", "timetable_type='food'ANDmeal<>''"},
    }
    return normalized in choices[name]


def physical(connection, loader):
    """Catalog-only 0042 representation and aggregate conflict counts; no PII."""
    objects, issues, present, baseline_issues = {}, [], [], []
    with connection.cursor() as cursor:
        for table, (model, added, new_table) in layout(loader).items():
            cursor.execute('SELECT a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull '
                           'FROM pg_attribute a WHERE a.attrelid=to_regclass(%s) AND a.attnum>0 AND NOT a.attisdropped '
                           'ORDER BY a.attnum', ['public.' + table])
            cols = {name: (kind, not notnull) for name, kind, notnull in cursor.fetchall()}
            expected = model._meta.local_fields if new_table else added
            objects[table] = {'exists': bool(cols), 'columns': sorted(cols)}
            if not new_table:
                baseline = [f.column for f in model._meta.local_fields if f not in added]
                baseline_issues.extend(table + '.' + name for name in baseline if name not in cols)
            if new_table and cols:
                present.append(table)
            for field in expected:
                if field.column in cols:
                    present.append(table + '.' + field.column)
                actual = cols.get(field.column)
                db_type = field.db_type(connection)
                normalized = db_type.replace('varchar', 'character varying') if db_type else None
                if actual != (normalized, field.null):
                    issues.append(table + '.' + field.column)
            if cols:
                constraints = connection.introspection.get_constraints(cursor, table)
                for field in expected:
                    candidates = [c for c in constraints.values() if c['columns'] == [field.column]]
                    if field.primary_key and not any(c['primary_key'] for c in candidates):
                        issues.append(table + '.' + field.column + ':primary_key')
                    if field.unique and not any(c['unique'] or c['primary_key'] for c in candidates):
                        issues.append(table + '.' + field.column + ':unique')
                    if field.remote_field:
                        target = (field.remote_field.model._meta.db_table, field.target_field.column)
                        if not any(c['foreign_key'] == target for c in candidates):
                            issues.append(table + '.' + field.column + ':foreign_key')
        constraint_snapshot = {}
        for name, (table, columns, conditional) in CONSTRAINTS.items():
            cursor.execute('SELECT i.indisunique,i.indisvalid,pg_get_expr(i.indpred,i.indrelid), '
                           'ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY k(n,ord) '
                           'JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.n ORDER BY k.ord),i.indrelid::regclass::text '
                           'FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid '
                           'JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s', ['public', name])
            row = cursor.fetchone()
            constraint_snapshot[name] = list(row) if row else None
            if row:
                present.append(name)
            if not row or row[0:2] != (True, True) or row[3] != columns or row[4] != table or not expected_predicate(name,row[2]):
                issues.append(name)
        conflicts = {}
        for table, key, where in (
                ('dic_house', 'edition_id,canonical_key', "canonical_key<>''"),
                ('dic_timetableentry', 'edition_id,date,meal', "timetable_type='food' AND meal<>''")):
            needed = 'canonical_key' if table == 'dic_house' else 'meal'
            # Before 0042, these new columns are implicitly blank for all old rows.
            if needed in objects[table]['columns']:
                cursor.execute('SELECT count(*) FROM (SELECT 1 FROM ' + table + ' WHERE ' + where +
                               ' GROUP BY ' + key + ' HAVING count(*)>1) duplicates')
                conflicts[table] = cursor.fetchone()[0]
            else:
                conflicts[table] = 0
    probes = {}
    from django.db import transaction
    from config.startup_db_inspection import safe_error
    for table, (model, _, _) in layout(loader).items():
        columns = ','.join(connection.ops.quote_name(f.column) for f in model._meta.local_fields)
        try:
            with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
                cursor.execute('SELECT ' + columns + ' FROM ' + connection.ops.quote_name(table) + ' WHERE FALSE')
            probes[table] = {'sqlstate': None, 'ok': True}
        except Exception as exc:
            probes[table] = {**safe_error(exc), 'ok': False}
    return dict(objects=objects, constraints=constraint_snapshot, missing_or_incompatible=sorted(issues),
                present=sorted(set(present)), unique_conflicts=conflicts, zero_row_probes=probes,
                baseline_incompatible=sorted(baseline_issues))


def inspect(connection, executor, expected, commit):
    plan = graph(executor)
    require(('dic', '0041_phase_a_order_lifecycle') in executor.loader.applied_migrations,
            'APPROVED_0041_DEPENDENCY_NOT_APPLIED')
    shape = physical(connection, executor.loader)
    recorded = TARGET in executor.loader.applied_migrations
    state = ('applied' if not shape['missing_or_incompatible'] and not shape['baseline_incompatible'] else 'inconsistent') if recorded else (
        'inconsistent' if shape['present'] or shape['baseline_incompatible'] else 'missing')
    if any(shape['unique_conflicts'].values()):
        state = 'inconsistent'
    if recorded and any(not p['ok'] for p in shape['zero_row_probes'].values()):
        state = 'inconsistent'
    if not recorded and any(not p['ok'] and p['sqlstate'] not in ('42703','42P01')
                            for p in shape['zero_row_probes'].values()):
        state = 'inconsistent'
    pending = [{'app': m.app_label, 'name': m.name, 'source_sha256': source_hash(m)} for m, _ in plan]
    ancestry = executor.loader.graph.forwards_plan(TARGET)
    body = dict(release_commit=commit, target=list(TARGET), target_source_sha256=SOURCE_SHA256,
                identity=expected, state=state, schema=shape, pending=pending,
                recorded=sorted([list(n) for n in executor.loader.applied_migrations]),
                dependencies=[{'node': list(n), 'sha256': source_hash(executor.loader.graph.nodes[n])}
                              for n in ancestry if n != TARGET])
    return {**body, 'plan_sha256': digest(body)}, plan


def approve(manifest, approval):
    try:
        validate_approval(manifest, approval)
    except RuntimeError:
        raise Stop('APPROVAL_PLAN_OR_BACKUP_EVIDENCE_MISMATCH') from None
    require(approval.get('release_commit') == manifest['release_commit'], 'APPROVAL_RELEASE_MISMATCH')
    require(approval.get('reviewed_plan_sha256') == manifest['plan_sha256'], 'REVIEWED_FINGERPRINT_MISMATCH')
    require(approval.get('owner_authorized') is True and approval.get('backup_restore_verified') is True,
            'EXPLICIT_OWNER_AND_RECOVERY_APPROVAL_REQUIRED')


def execute(connection, transaction, executor_factory, mode, expected, commit, approval=None):
    require(mode in ('inspect', 'apply', 'verify'), 'EXPLICIT_MODE_REQUIRED')
    # Prevent unsafe endpoints before making the first connection.
    try:
        check_config(connection.settings_dict, expected)
    except Exception:
        raise Stop('TLS_OR_CONFIGURED_IDENTITY_REJECTED') from None
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            if mode != 'apply':
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute("SET LOCAL search_path = 'public'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute('SELECT pg_try_advisory_xact_lock(%s,%s)', LOCK)
            require(cursor.fetchone()[0] is True, 'MIGRATION_LOCK_BUSY')
        actual = identity(connection, expected)
        if mode == 'apply':
            # Stabilize catalog/constraint preconditions across the approved DDL.
            with connection.cursor() as cursor:
                cursor.execute('LOCK TABLE django_migrations,dic_house,dic_timetableentry,dic_campvideo IN SHARE ROW EXCLUSIVE MODE')
        executor = executor_factory(connection)
        manifest, plan = inspect(connection, executor, actual, commit)
        if mode == 'inspect':
            return {'status': 'INSPECTED_READ_ONLY', 'manifest': manifest}
        if mode == 'verify':
            require(manifest['state'] == 'applied' and not plan, 'SCHEMA_NOT_READY')
            return {'status': 'VERIFIED_READ_ONLY', 'manifest': manifest}
        if manifest['state'] == 'applied' and not plan:
            # A retry after an unknown COMMIT outcome must not reapply/fake anything.
            return {'status': 'ALREADY_APPLIED_NO_WRITES', 'manifest': manifest}
        require(manifest['state'] == 'missing', 'PARTIAL_OR_INCONSISTENT_SCHEMA_STOP')
        require(len(plan) == 1 and (plan[0][0].app_label, plan[0][0].name) == TARGET,
                'UNRELATED_OR_MISSING_PENDING_PLAN')
        require(not any(manifest['schema']['unique_conflicts'].values()), 'EXISTING_UNIQUE_CONFLICTS')
        approve(manifest, approval)
        executor.migrate([TARGET], plan=plan)
        checked = executor_factory(connection)
        after, pending = inspect(connection, checked, actual, commit)
        require(after['state'] == 'applied' and not pending, 'POST_APPLY_VERIFICATION_FAILED')
        result = {'status': 'COMMITTED_0042', 'reviewed_plan_sha256': manifest['plan_sha256'], 'manifest': after}
    # Return only after the enclosing PostgreSQL transaction COMMIT succeeds.
    return result


def run(recovery=True):
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        mode, expected, commit, approval = environment(os.environ, recovery)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            from django.conf import settings
            # Set read-only at connection creation, before app initialization.
            if mode != 'apply':
                opts = settings.DATABASES['default'].setdefault('OPTIONS', {})
                opts['options'] = '-c default_transaction_read_only=on'
            import django
            django.setup()
            from django.db import connection, transaction
            from django.db.migrations.executor import MigrationExecutor
            try:
                if recovery:
                    receipt = execute(connection, transaction, MigrationExecutor, mode, expected, commit, approval)
                else:
                    from config.deployment_schema_guard import readiness
                    receipt = readiness(connection, transaction, MigrationExecutor, expected, commit)
            finally:
                connection.close()
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except Exception as exc:
        # Never print database errors, environment values, DSNs or SQL parameters.
        code = str(exc) if type(exc) is Stop else (
            'APPLY_OUTCOME_UNCONFIRMED_REINSPECT' if locals().get('mode') == 'apply'
            else 'INSPECTION_FAILED_REVIEW_PRIVATELY')
        print('[schema-recovery] STOP: ' + code, file=sys.stderr)
        return 1
    finally:
        logging.disable(previous_logging)


if __name__ == '__main__':
    sys.exit(run())
