"""Owner-approved, non-promoting migration for DIC 0048 carousel tables.

No database connection on import. Only an explicitly enabled Render build invokes
this runner; it refuses to apply until a reviewed fresh backup checksum is pinned
in source and independently confirmed through the deployment environment.
"""
import contextlib
import hashlib
from importlib import import_module
import logging
import os
from pathlib import Path
import re
import sys

from config.integrated_schema_recovery import identity

APPROVAL = 'APPROVE-DAWANA-CAROUSELS-0048'
# Replace with the reviewed SHA-256 of a NEW readable production backup.
# Unset deliberately fails closed; the previous 0047 backup is not acceptable.
APPROVED_FRESH_BACKUP_SHA256 = 'UNSET_PENDING_FRESH_0048_BACKUP'
EXPECTED_DATABASE = 'dawana_db'
EXPECTED_ROLE = 'dawana_db_user'
EXPECTED_CLUSTER = '7705861322388955175'
MIGRATION_BLOB_SHA = '067ce909ca1da8738af3145af8c1cbe81e6201be'
TARGET = ('dic', '0048_studio_carousels')
PREREQUISITE = ('dic', '0047_studio_publications')
LOCK = (17428041, 48)
MODEL_NAMES = ('StudioCarousel', 'StudioCarouselSlide', 'StudioCarouselPlacement')
TABLE_NAMES = ('dic_studiocarousel', 'dic_studiocarouselslide', 'dic_studiocarouselplacement')


class Stop(RuntimeError):
    pass


def must(condition, code):
    if not condition:
        raise Stop(code)


def validate_approval(env, settings_module, config):
    must(settings_module == 'config.settings.render', 'RENDER_SETTINGS_REQUIRED')
    must(env.get('RENDER') == 'true', 'RENDER_REQUIRED')
    must(re.fullmatch(r'[0-9a-f]{40}', env.get('RENDER_GIT_COMMIT', '')) is not None,
         'RELEASE_COMMIT_REQUIRED')
    must(env.get('DAWANA_0048_APPROVAL') == APPROVAL, 'OWNER_APPROVAL_REQUIRED')
    must(re.fullmatch(r'[A-Fa-f0-9]{64}', APPROVED_FRESH_BACKUP_SHA256) is not None,
         'FRESH_BACKUP_NOT_PINNED_IN_CODE')
    must(env.get('DAWANA_0048_FRESH_BACKUP_SHA256') == APPROVED_FRESH_BACKUP_SHA256,
         'BACKUP_DIGEST_MISMATCH')
    must(env.get('DAWANA_0048_ARCHIVE_READABLE') == 'yes', 'BACKUP_NOT_VERIFIED_READABLE')
    must(config.get('NAME') == EXPECTED_DATABASE and config.get('USER') == EXPECTED_ROLE
         and str(config.get('PORT') or '5432') == '5432',
         'PRODUCTION_DATABASE_IDENTITY_MISMATCH')
    return {'database': EXPECTED_DATABASE, 'role': EXPECTED_ROLE,
            'cluster_id': EXPECTED_CLUSTER, 'host': str(config.get('HOST') or ''),
            'port': str(config.get('PORT') or '5432')}


def verify_migration(migration):
    must(migration.atomic, 'MIGRATION_MUST_BE_ATOMIC')
    module = import_module(migration.__class__.__module__)
    raw = Path(module.__file__).read_bytes()
    git_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\x00' + raw).hexdigest()
    must(git_blob == MIGRATION_BLOB_SHA, 'MIGRATION_SOURCE_MISMATCH')
    from django.db.migrations.operations.models import CreateModel, AddConstraint
    ops = migration.operations
    must(len(ops) == 5 and
         all(type(op) is CreateModel for op in ops[:3]) and
         all(type(op) is AddConstraint for op in ops[3:]) and
         {op.name for op in ops[:3]} == set(MODEL_NAMES) and
         {op.constraint.name for op in ops[3:]} ==
         {'dic_carousel_slide_order_unique', 'dic_carousel_one_destination'},
         'MIGRATION_OPERATIONS_CHANGED')
    must(PREREQUISITE in migration.dependencies, 'MIGRATION_DEPENDENCY_CHANGED')


def verify_tables(cursor, expected_present):
    placeholders = ','.join(['to_regclass(%s) IS NOT NULL'] * len(TABLE_NAMES))
    cursor.execute('SELECT ' + placeholders, ['public.' + name for name in TABLE_NAMES])
    must(cursor.fetchone() == (expected_present,) * len(TABLE_NAMES),
         'CAROUSEL_SCHEMA_NOT_IN_EXPECTED_STATE')


def apply_exact_0048():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    expected = validate_approval(os.environ, settings.SETTINGS_MODULE, connection.settings_dict)
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path = 'public'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute('SELECT pg_try_advisory_xact_lock(%s,%s)', LOCK)
            must(cursor.fetchone() == (True,), 'MIGRATION_LOCK_BUSY')
        identity(connection, expected)
        executor = MigrationExecutor(connection)
        loader = executor.loader
        loader.check_consistent_history(connection)
        must(not loader.detect_conflicts(), 'MIGRATION_GRAPH_CONFLICT')
        must(PREREQUISITE in loader.applied_migrations, 'PREREQUISITE_0047_NOT_APPLIED')
        must(TARGET in loader.graph.nodes, 'TARGET_MIGRATION_MISSING')
        must(TARGET not in loader.applied_migrations, 'MIGRATION_ALREADY_APPLIED')
        plan = executor.migration_plan(loader.graph.leaf_nodes())
        must(len(plan) == 1 and not plan[0][1] and
             (plan[0][0].app_label, plan[0][0].name) == TARGET,
             'UNEXPECTED_PENDING_MIGRATION_PLAN')
        verify_migration(plan[0][0])
        with connection.cursor() as cursor:
            verify_tables(cursor, False)
        executor.migrate([TARGET], plan=plan)
        # Executor.migrate() does not emit post_migrate in this procedure.
        # Create only the default permissions for these newly introduced models.
        from django.apps import apps
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        for model_name in MODEL_NAMES:
            model = apps.get_model('dic', model_name)
            content_type, _ = ContentType.objects.get_or_create(
                app_label='dic', model=model._meta.model_name)
            for action in model._meta.default_permissions:
                Permission.objects.get_or_create(
                    content_type=content_type,
                    codename=f'{action}_{model._meta.model_name}',
                    defaults={'name': f'Can {action} {model._meta.verbose_name}'})
        refreshed = MigrationExecutor(connection)
        must(TARGET in refreshed.loader.applied_migrations and
             not refreshed.migration_plan(refreshed.loader.graph.leaf_nodes()),
             'POST_APPLY_MIGRATION_PLAN_NOT_EMPTY')
        with connection.cursor() as cursor:
            verify_tables(cursor, True)
            cursor.execute(
                "SELECT count(*) FROM auth_permission p "
                "JOIN django_content_type c ON c.id=p.content_type_id "
                "WHERE c.app_label='dic' AND c.model IN "
                "('studiocarousel','studiocarouselslide','studiocarouselplacement') "
                "AND p.codename LIKE '%%_' || c.model"
            )
            must(cursor.fetchone()[0] >= 12, 'CAROUSEL_MODEL_PERMISSIONS_MISSING')
    return '0048_TRANSACTION_COMMITTED'


def main():
    logging.disable(logging.CRITICAL)
    try:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import django
            django.setup()
            from django.db import connection
            try:
                result = apply_exact_0048()
            finally:
                connection.close()
        print('[carousel-0048] ' + result)
        return 0
    except Exception as exc:
        print('[carousel-0048] STOP: ' +
              (str(exc) if type(exc) is Stop else 'UNEXPECTED_FAILURE_REVIEW_PRIVATELY'),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
