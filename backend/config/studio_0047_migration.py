"""One-time fail-closed DIC 0047 migration for DAWANA production.

No work on import. Only run via the explicitly authorized, deliberately
non-promoting Render build wrapper. The archive hash must be pinned by code
review after a *fresh* production backup has been checked.
"""
import contextlib
import hashlib
from pathlib import Path
import logging
import os
import re
import sys

APPROVAL = 'APPROVE-DAWANA-MEDIA-0047'
# Intentionally non-executable until the fresh archive SHA-256 is committed.
APPROVED_FRESH_BACKUP_SHA256 = '58C489B4A7A3C699725B676B25B462ABC80B25C835B97F3ECC817219AB0BF4B3'
EXPECTED_DATABASE = 'dawana_db'
EXPECTED_ROLE = 'dawana_db_user'
EXPECTED_CLUSTER = '7705861322388955175'
MIGRATION_BLOB_SHA = '06b71ca299eb9b1c9557916590e37589808f31c9'
TARGET = ('dic', '0047_studio_publications')
LOCK = (17428041, 47)


class Stop(RuntimeError):
    pass


def must(value, reason):
    if not value:
        raise Stop(reason)


def apply_exact_0047():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.operations.models import CreateModel
    from config.integrated_schema_recovery import identity
    must(settings.SETTINGS_MODULE == 'config.settings.render', 'RENDER_SETTINGS_REQUIRED')
    must(os.environ.get('RENDER') == 'true', 'RENDER_REQUIRED')
    must(re.fullmatch(r'[0-9a-f]{40}', os.environ.get('RENDER_GIT_COMMIT', '')),
         'DEPLOY_COMMIT_REQUIRED')
    must(os.environ.get('DAWANA_0047_APPROVAL') == APPROVAL, 'EXPLICIT_APPROVAL_REQUIRED')
    must(len(APPROVED_FRESH_BACKUP_SHA256) == 64 and
         all(x in '0123456789abcdefABCDEF' for x in APPROVED_FRESH_BACKUP_SHA256),
         'FRESH_BACKUP_SHA_NOT_REVIEWED_IN_CODE')
    must(os.environ.get('DAWANA_0047_FRESH_BACKUP_SHA256') == APPROVED_FRESH_BACKUP_SHA256,
         'EXACT_VERIFIED_BACKUP_REQUIRED')
    must(os.environ.get('DAWANA_0047_ARCHIVE_READABLE') == 'yes', 'BACKUP_ARCHIVE_VALIDATION_REQUIRED')
    must(connection.settings_dict.get('NAME') == EXPECTED_DATABASE and
         connection.settings_dict.get('USER') == EXPECTED_ROLE and
         str(connection.settings_dict.get('PORT') or '5432') == '5432',
         'UNEXPECTED_DATABASE_IDENTITY')
    expected = {
        'database': EXPECTED_DATABASE, 'role': EXPECTED_ROLE, 'cluster_id': EXPECTED_CLUSTER,
        'host': str(connection.settings_dict.get('HOST') or ''),
        'port': str(connection.settings_dict.get('PORT') or '5432')
    }
    with transaction.atomic():
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
        must(('dic', '0046_aftercamp_assessments') in loader.applied_migrations,
             'APPROVED_DEPENDENCY_MISSING')
        must(TARGET in loader.graph.nodes, 'MIGRATION_0047_NOT_IN_RELEASE')
        must(TARGET not in loader.applied_migrations, 'MIGRATION_ALREADY_APPLIED')
        plan = executor.migration_plan(loader.graph.leaf_nodes())
        must(len(plan) == 1 and (plan[0][0].app_label, plan[0][0].name) == TARGET
             and plan[0][1] is False, 'UNREVIEWED_PENDING_MIGRATION')
        migration = plan[0][0]
        from importlib import import_module
        module = import_module(migration.__class__.__module__)
        source = Path(module.__file__).read_bytes()
        blob_sha = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\x00' + source).hexdigest()
        must(blob_sha == MIGRATION_BLOB_SHA, 'MIGRATION_0047_SOURCE_MISMATCH')
        must(migration.atomic and len(migration.operations) == 2
             and all(type(op) is CreateModel for op in migration.operations),
             'MIGRATION_0047_OPERATIONS_CHANGED')
        must({op.name for op in migration.operations} == {'StudioCollection', 'StudioPublication'},
             'MIGRATION_0047_MODELS_CHANGED')
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.dic_studiocollection') IS NULL,"
                           "to_regclass('public.dic_studiopublication') IS NULL")
            must(cursor.fetchone() == (True, True), 'PARTIAL_OR_EXISTING_0047_SCHEMA')
        executor.migrate([TARGET], plan=plan)
        # Mirror the verified 0046 pathway: migration run bypasses post_migrate,
        # so explicitly add only permissions for these new publication models.
        from django.apps import apps
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        for model_name in ('StudioCollection', 'StudioPublication'):
            model = apps.get_model('dic', model_name)
            content_type, _ = ContentType.objects.get_or_create(
                app_label='dic', model=model._meta.model_name)
            for action in model._meta.default_permissions:
                Permission.objects.get_or_create(
                    content_type=content_type,
                    codename=f'{action}_{model._meta.model_name}',
                    defaults={'name': f'Can {action} {model._meta.verbose_name}'})
        refreshed = MigrationExecutor(connection)
        must(TARGET in refreshed.loader.applied_migrations
             and not refreshed.migration_plan(refreshed.loader.graph.leaf_nodes()),
             'MIGRATION_0047_POSTVERIFY_FAILED')
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.dic_studiocollection') IS NOT NULL,"
                           "to_regclass('public.dic_studiopublication') IS NOT NULL")
            must(cursor.fetchone() == (True, True), 'MIGRATION_0047_TABLES_MISSING')
            cursor.execute("SELECT count(*) FROM auth_permission p "
                           "JOIN django_content_type c ON p.content_type_id=c.id "
                           "WHERE c.app_label='dic' AND c.model IN "
                           "('studiocollection','studiopublication') AND p.codename LIKE '%%_' || c.model")
            must(cursor.fetchone()[0] >= 8, 'MIGRATION_0047_PERMISSIONS_MISSING')
    return '0047_TRANSACTION_COMMITTED'


def main():
    logging.disable(logging.CRITICAL)
    try:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render'
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import django
            django.setup()
            from django.db import connection
            try:
                result = apply_exact_0047()
            finally:
                connection.close()
        print('[media-0047] ' + result)
        return 0
    except Exception as exc:
        print('[media-0047] STOP: ' +
              (str(exc) if type(exc) is Stop else 'UNEXPECTED_FAILURE_REVIEW_PRIVATELY'),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
