"""Read-only planning by default; explicit reviewed manifest for application."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from config.release_migrations import plan_manifest,validate_approval,validate_target


class Command(BaseCommand):
    help='Inspect the exact pending plan. Application requires a separately approved manifest.'

    def add_arguments(self,parser):
        parser.add_argument('--database-name',required=True)
        parser.add_argument('--hostname', required=True)
        parser.add_argument('--port', required=True)
        parser.add_argument('--role', required=True)
        parser.add_argument('--cluster-id', required=True)
        parser.add_argument('--approval-file')
        parser.add_argument('--apply-approved-plan',action='store_true')
        parser.add_argument('--manifest-file',help='Write the exact read-only plan as JSON for review.')

    def handle(self,*args,**options):
        module=settings.SETTINGS_MODULE
        if module not in ('config.settings.production','config.settings.staging','config.settings.zevcloud'):
            raise CommandError('Release planning requires explicit staging/production settings.')
        name=options['database_name']
        if name in ('dawana_dev','dic_2026_demo','postgres','template0','template1') or settings.DATABASES['default']['NAME']!=name:
            raise CommandError('Release database identity rejected.')
        expected = dict(database=name, host=options['hostname'], port=options['port'],
                        role=options['role'], cluster_id=options['cluster_id'])
        try:
            # Reject the wrong configured endpoint before opening a connection.
            validate_target(settings.DATABASES['default'], expected,
                            dict(database=name, role=expected['role'], cluster_id=expected['cluster_id']))
        except RuntimeError as exc:
            raise CommandError(str(exc)) from None
        with connection.cursor() as cursor:
            # Requires an explicitly authorized inspection role. If the managed
            # provider forbids this function, stop; do not bypass cluster binding.
            cursor.execute('SELECT current_database(), current_user, system_identifier::text '
                           'FROM pg_control_system()')
            actual = dict(zip(('database', 'role', 'cluster_id'), cursor.fetchone()))
        try:
            validate_target(settings.DATABASES['default'], expected, actual)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from None
        executor=MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        if executor.loader.detect_conflicts(): raise CommandError('Migration graph conflicts.')
        targets=executor.loader.graph.leaf_nodes()
        plan=executor.migration_plan(targets)
        manifest=plan_manifest(executor.loader,plan,name,module, {**expected, **actual})
        if not options['apply_approved_plan']:
            if options.get('manifest_file'):
                path=Path(options['manifest_file'])
                # Preserve evidence; never replace an existing approval/receipt.
                with path.open('x',encoding='utf-8') as output:
                    json.dump(manifest,output,indent=2)
            self.stdout.write(json.dumps(manifest,indent=2))
            if plan: raise CommandError('Pending migrations require approval of this exact plan; nothing applied.')
            self.stdout.write('PASS: no pending migrations.');return
        if not options['approval_file']: raise CommandError('An approved manifest is required.')
        try:
            approval=json.loads(Path(options['approval_file']).read_text(encoding='utf-8'))
            validate_approval(manifest,approval)
        except (OSError,ValueError,RuntimeError):
            raise CommandError('Missing, invalid or mismatched migration approval.') from None
        # Deployment operators must separately approve this command. No startup
        # hook supplies the application flag or bypasses a pending plan.
        executor.migrate(targets,plan=plan)
        if plan:
            from django.core.management.sql import emit_post_migrate_signal
            emit_post_migrate_signal(verbosity=options.get('verbosity',1),interactive=False,db='default')
        if executor.migration_plan(targets):
            # Rebuild loader: the original executor holds its pre-application state.
            refreshed=MigrationExecutor(connection)
            if refreshed.migration_plan(refreshed.loader.graph.leaf_nodes()):
                raise CommandError('Required schema remains pending; release blocked.')
        self.stdout.write('Approved migration plan completed. Cache-table approval remains a separate release gate.')
