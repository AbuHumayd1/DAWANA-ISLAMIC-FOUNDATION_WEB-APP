"""One-time read-only Media Studio migration plan for Render's shell-less service.

Run only through studio-migration-inspect-build.sh on an explicitly selected
commit. No migrations, release SQL or data-writing commands are executed.
"""
import json
import os

from config.integrated_schema_recovery import Stop, environment, identity, require
from config.release_migrations import plan_manifest


ALLOWED = (
    ("dic", "0043_exclude_dic2026_millionaire_drafts"),
    ("dic", "0044_studio_catalogue_placements"),
    ("dic", "0045_studio_hosted_video"),
)


def inspection():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    require(settings.SETTINGS_MODULE == "config.settings.render",
            "RENDER_SETTINGS_REQUIRED")
    _, expected, commit, _ = environment(os.environ, recovery=False)
    require(commit == os.environ.get("DAWANA_STUDIO_INSPECT_COMMIT"),
            "PINNED_INSPECTION_COMMIT_MISMATCH")
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL search_path = 'public'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        actual = identity(connection, expected)
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        require(not executor.loader.detect_conflicts(), "MIGRATION_GRAPH_CONFLICT")
        require(("dic", "0042_integrated_camp_2026") in executor.loader.applied_migrations,
                "MIGRATION_0042_NOT_RECORDED")
        require(all(m in executor.loader.graph.nodes for m in ALLOWED),
                "EXPECTED_MIGRATION_MISSING")
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        require(not any(backwards for _, backwards in plan), "BACKWARD_MIGRATION_BLOCKED")
        pending = tuple((migration.app_label, migration.name) for migration, _ in plan)
        # This is the only approved pending set. Applied successors are permitted
        # only when the remaining pending items form the exact suffix.
        require(pending in ((), ALLOWED, ALLOWED[1:], ALLOWED[2:]),
                "UNEXPECTED_OR_UNRELATED_MIGRATION_PLAN")
        manifest = plan_manifest(executor.loader, plan, expected["database"],
                                 settings.SETTINGS_MODULE, actual)
        # Includes SHA-256 of all pending source files, migration dependencies
        # and exact pinned production endpoint identity; no DB credentials.
        print("[studio-migration] INSPECTED_READ_ONLY", flush=True)
        print("[studio-migration] MANIFEST_BEGIN", flush=True)
        print(json.dumps({"release_commit": commit, "manifest": manifest},
                         sort_keys=True, indent=2), flush=True)
        print("[studio-migration] MANIFEST_END", flush=True)
        print("[studio-migration] PENDING_COUNT=" + str(len(plan)), flush=True)


if __name__ == "__main__":
    # No broad catch: fail closed. Never log environment or DB connection URL.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.render")
    import django
    django.setup()
    inspection()
