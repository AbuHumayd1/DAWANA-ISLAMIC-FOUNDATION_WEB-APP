"""Read-only Render build barrier. No schema modification or startup dependency."""
import sys
from config.integrated_schema_recovery import Stop, require, identity, graph, run, check_config, physical


def readiness(connection, transaction, executor_factory, expected, commit):
    try:
        check_config(connection.settings_dict, expected)
    except Exception:
        raise Stop('TLS_OR_CONFIGURED_IDENTITY_REJECTED') from None
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute("SET LOCAL search_path = 'public'")
            cursor.execute("SET LOCAL lock_timeout = '3s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        identity(connection, expected)
        executor = executor_factory(connection)
        pending = graph(executor, pinned=False)
        require(not pending, 'UNAPPLIED_MIGRATIONS_RUN_REVIEWED_MIGRATION_PROCEDURE')
        schema = physical(connection, executor.loader)
        require(not schema['missing_or_incompatible'] and not schema['baseline_incompatible']
                and not any(schema['unique_conflicts'].values()),
                'RECORDED_SCHEMA_INCOMPATIBLE')
        # Detect fake/partial history even when the recorder claims compatibility.
        from django.apps import apps
        with connection.cursor() as cursor:
            for model in apps.get_models(include_auto_created=True):
                if not model._meta.managed or model._meta.proxy:
                    continue
                columns = ','.join(connection.ops.quote_name(f.column) for f in model._meta.local_fields)
                try:
                    with transaction.atomic(using=connection.alias):
                        cursor.execute('SELECT ' + columns + ' FROM ' + connection.ops.quote_name(model._meta.db_table) + ' WHERE FALSE')
                except Exception:
                    raise Stop('RECORDED_SCHEMA_INCOMPATIBLE') from None
        return {'status': 'DEPLOYMENT_SCHEMA_READY_READ_ONLY', 'release_commit': commit,
                'migration_nodes': len(executor.loader.applied_migrations)}


if __name__ == '__main__':
    sys.exit(run(recovery=False))
