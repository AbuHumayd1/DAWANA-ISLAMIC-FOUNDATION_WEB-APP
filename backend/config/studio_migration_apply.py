"""Owner-gated, one-time, exact-plan DAWANA Media Studio production migration.

Importing this module does nothing. Only a deliberately failed Render build
may invoke it; no application promotion, no implicit startup migrations.
"""
import contextlib
import logging
import os
import sys

from config.integrated_schema_recovery import Stop, identity, require
from config.release_migrations import plan_manifest
from config.studio_migration_inspect import (
    APPROVED_DATABASE, APPROVED_ROLE, APPROVED_CLUSTER_ID, ALLOWED,
)

# Plan obtained from the read-only Render inspection at commit 91c0a21.
APPROVED_PLAN_SHA256 = "8f9bdc37f34dbb9978e755c3a3fdf683bd8ef7d785143aa08f3395d6cddcc8c5"
BACKUP_REFERENCE = "dawana_db-20261117-225034.dump"
BACKUP_SHA256 = "EAA4A392867D37F7A23BC793B6E89FE079001D8F5B7373A936F65A899B4DF64B"
# A validated archive is not a restored backup. Approval is separate.
EXPLICIT_APPROVAL = "APPROVE-DAWANA-STUDIO-0043-0045"


def apply_approved_migrations():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.operations.fields import AlterField
    from django.db.migrations.operations.models import CreateModel, AddConstraint
    from django.db.migrations.operations.special import RunPython

    require(settings.SETTINGS_MODULE == "config.settings.render",
            "RENDER_SETTINGS_REQUIRED")
    require(os.environ.get("RENDER") == "true", "RENDER_REQUIRED")
    require(os.environ.get("DAWANA_STUDIO_MIGRATION_APPROVAL") == EXPLICIT_APPROVAL,
            "EXPLICIT_OWNER_APPROVAL_REQUIRED")
    require(os.environ.get("DAWANA_STUDIO_BACKUP_VERIFIED") == BACKUP_SHA256,
            "BACKUP_CONFIRMATION_REQUIRED")
    config = connection.settings_dict
    expected = {
        "database": APPROVED_DATABASE, "role": APPROVED_ROLE,
        "cluster_id": APPROVED_CLUSTER_ID,
        "host": str(config.get("HOST") or ""), "port": "5432",
    }
    require(config.get("NAME") == APPROVED_DATABASE and
            config.get("USER") == APPROVED_ROLE and
            str(config.get("PORT") or "5432") == "5432",
            "PRODUCTION_DATABASE_IDENTITY_MISMATCH")
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path='public'")
            cursor.execute("SET LOCAL lock_timeout='5s'")
            cursor.execute("SET LOCAL statement_timeout='120s'")
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s,%s)", [17428041, 45])
            require(cursor.fetchone() == (True,), "MIGRATION_LOCK_BUSY")
        actual = identity(connection, expected)
        executor = MigrationExecutor(connection)
        loader = executor.loader
        loader.check_consistent_history(connection)
        require(not loader.detect_conflicts(), "MIGRATION_GRAPH_CONFLICT")
        require(("dic", "0042_integrated_camp_2026") in loader.applied_migrations,
                "0042_DEPENDENCY_NOT_APPLIED")
        require(all(node in loader.graph.nodes for node in ALLOWED),
                "EXPECTED_MIGRATION_MISSING")
        targets = loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = tuple((m.app_label, m.name) for m, backwards in plan)
        require(pending == ALLOWED and all(not backwards for _, backwards in plan),
                "UNEXPECTED_PENDING_MIGRATIONS")
        ops = {m.name: m.operations for m, _ in plan}
        require(
            len(ops[ALLOWED[0][1]]) == 1
            and type(ops[ALLOWED[0][1]][0]) is RunPython
            and len(ops[ALLOWED[1][1]]) == 6
            and all(type(op) in (CreateModel, AddConstraint) for op in ops[ALLOWED[1][1]])
            and len(ops[ALLOWED[2][1]]) == 2
            and type(ops[ALLOWED[2][1]][0]) is AlterField
            and type(ops[ALLOWED[2][1]][1]) is CreateModel,
            "MIGRATION_OPERATIONS_CHANGED")
        manifest = plan_manifest(loader, plan, APPROVED_DATABASE,
                                 settings.SETTINGS_MODULE, actual)
        require(manifest["plan_sha256"] == APPROVED_PLAN_SHA256,
                "EXACT_INSPECTED_MANIFEST_MISMATCH")
        # The custom 0043 cleanup matches only old excluded draft records.
        # A current zero-target preflight was reviewed separately.
        executor.migrate(targets, plan=plan)
        refreshed = MigrationExecutor(connection)
        require(
            all(node in refreshed.loader.applied_migrations for node in ALLOWED)
            and not refreshed.migration_plan(refreshed.loader.graph.leaf_nodes()),
            "SCHEMA_NOT_FULLY_APPLIED")
        # The separate build never invokes Django's post_migrate signal.
        # Create only Studio content types / permissions, never assign roles.
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from dic.studio_models import StudioAsset, StudioPlacement
        from dic.studio_hosted_models import StudioHostedVideo
        for model in (StudioAsset, StudioPlacement, StudioHostedVideo):
            ct, _ = ContentType.objects.get_or_create(
                app_label="dic", model=model._meta.model_name)
            definitions = [
                (f"{action}_{model._meta.model_name}",
                 f"Can {action} {model._meta.verbose_name}")
                for action in model._meta.default_permissions
            ]
            definitions.extend(model._meta.permissions)
            for codename, label in definitions:
                Permission.objects.get_or_create(
                    content_type=ct, codename=codename,
                    defaults={"name": label})
        # This transaction commits all 3 steps together, or rolls back on error.
    print("[studio-migration] APPLIED_EXACT_PLAN=" + APPROVED_PLAN_SHA256)
    print("[studio-migration] MIGRATIONS_0043_0044_0045_RECORDED")


def main():
    logging.disable(logging.CRITICAL)
    try:
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.render"
        # Never print credentials, SQL errors or values from the environment.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import django
            django.setup()
            from django.db import connection
            try:
                apply_approved_migrations()
            finally:
                connection.close()
        print("[studio-migration] APPLICATION_COMPLETE; verify by read-only DB query")
        return 0
    except Exception as exc:
        print("[studio-migration] STOP: " +
              (str(exc) if type(exc) is Stop else "INTERNAL_FAILURE_REVIEW_PRIVATELY"),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
