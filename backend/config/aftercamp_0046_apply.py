"""One-time owner-approved migration 0046; invoked only by a deliberately failed Render build."""
import contextlib
import hashlib
import logging
import os
from pathlib import Path
import re
import sys

from config.integrated_schema_recovery import Stop, identity, require

APPROVAL = "APPROVE-DAWANA-AFTERCAMP-0046"
BACKUP_SHA256 = "BC1920714254A5F7FB78F4FE5B005E9BFB1F1137DC12776172F2A7ECB83D064F"
CLUSTER_ID = "7705861322388955175"
MIGRATION_BLOB_SHA = "c039778daf527af81556e1166d80ee5fcc7523a5"
EXPECTED = (("dic", "0046_aftercamp_assessments"),)


def apply():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.operations.models import AddConstraint, CreateModel

    require(settings.SETTINGS_MODULE == "config.settings.render", "RENDER_SETTINGS_REQUIRED")
    require(os.environ.get("RENDER") == "true", "RENDER_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{40}", os.environ.get("RENDER_GIT_COMMIT", "")),
            "DEPLOY_COMMIT_REQUIRED")
    require(os.environ.get("DAWANA_AFTERCAMP_0046_APPROVAL") == APPROVAL,
            "EXPLICIT_OWNER_APPROVAL_REQUIRED")
    require(os.environ.get("DAWANA_AFTERCAMP_0046_BACKUP_SHA256") == BACKUP_SHA256,
            "BACKUP_EVIDENCE_MISMATCH")

    config = connection.settings_dict
    require(config.get("NAME") == "dawana_db"
            and config.get("USER") == "dawana_db_user"
            and str(config.get("PORT") or "5432") == "5432",
            "PRODUCTION_DATABASE_IDENTITY_MISMATCH")
    expected = {
        "database": "dawana_db", "role": "dawana_db_user",
        "cluster_id": CLUSTER_ID, "host": str(config.get("HOST") or ""),
        "port": "5432",
    }
    require(bool(expected["host"]), "PRODUCTION_HOST_MISSING")
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path='public'")
            cursor.execute("SET LOCAL lock_timeout='5s'")
            cursor.execute("SET LOCAL statement_timeout='120s'")
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s,%s)", [17428041, 46])
            require(cursor.fetchone() == (True,), "MIGRATION_LOCK_BUSY")
        identity(connection, expected)
        executor = MigrationExecutor(connection)
        loader = executor.loader
        loader.check_consistent_history(connection)
        require(not loader.detect_conflicts(), "MIGRATION_GRAPH_CONFLICT")
        require(("dic", "0045_studio_hosted_video") in loader.applied_migrations,
                "PREREQUISITE_0045_NOT_APPLIED")
        require(EXPECTED[0] in loader.graph.nodes, "MIGRATION_0046_NOT_FOUND")
        plan = executor.migration_plan(loader.graph.leaf_nodes())
        pending = tuple((m.app_label, m.name) for m, _ in plan)
        require(pending == EXPECTED and all(not backwards for _, backwards in plan),
                "UNEXPECTED_PENDING_MIGRATION_PLAN")
        migration = plan[0][0]
        module = __import__(migration.__class__.__module__, fromlist=["__file__"])
        source = Path(module.__file__).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\x00" + source).hexdigest()
        require(blob == MIGRATION_BLOB_SHA, "MIGRATION_SOURCE_MISMATCH")
        operations = migration.operations
        require(migration.atomic and len(operations) == 2
                and type(operations[0]) is CreateModel
                and operations[0].name == "AftercampAssessment"
                and type(operations[1]) is AddConstraint
                and operations[1].constraint.name == "dic_aftercamp_topic_edition_unique",
                "MIGRATION_OPERATIONS_MISMATCH")
        executor.migrate(loader.graph.leaf_nodes(), plan=plan)
        refreshed = MigrationExecutor(connection)
        require(EXPECTED[0] in refreshed.loader.applied_migrations
                and not refreshed.migration_plan(refreshed.loader.graph.leaf_nodes()),
                "MIGRATION_0046_NOT_VERIFIED")
        # Create only the standard permissions for this new model.
        from django.apps import apps
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        model = apps.get_model("dic", "AftercampAssessment")
        content_type, _ = ContentType.objects.get_or_create(
            app_label="dic", model=model._meta.model_name)
        for action in model._meta.default_permissions:
            Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"{action}_{model._meta.model_name}",
                defaults={"name": f"Can {action} {model._meta.verbose_name}"},
            )


def main():
    logging.disable(logging.CRITICAL)
    try:
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.render"
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import django
            django.setup()
            try:
                apply()
            finally:
                from django.db import connection
                connection.close()
        print("[aftercamp-0046] APPLICATION_COMPLETE; verify using read-only database query")
        return 0
    except Exception as exc:
        print("[aftercamp-0046] STOP: " +
              (str(exc) if type(exc) is Stop else "INTERNAL_FAILURE_REVIEW_PRIVATELY"),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
