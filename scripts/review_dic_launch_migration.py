"""Source-only launch migration review. No database inspection or test programme."""
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def denied(*args,**kwargs):
    raise RuntimeError('Database/network access is prohibited in source migration review.')


def main():
    try:
        from django.db.backends.base.base import BaseDatabaseWrapper
        with ExitStack() as stack:
            stack.enter_context(patch.object(BaseDatabaseWrapper,'ensure_connection',denied))
            stack.enter_context(patch.object(socket.socket,'connect',denied))
            stack.enter_context(patch.object(socket.socket,'connect_ex',denied))
            spec=importlib.util.spec_from_file_location('source_review_isolation',ROOT/'scripts/validate_dic_finance.py')
            helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
            credentials=helper.configure('test_dic_launch_source_review_unused')
            helper.guards(stack,credentials,no_database=True)
            from django.apps import apps
            from django.core.management import call_command
            from django.db.migrations import CreateModel
            from django.db.migrations.loader import MigrationLoader
            from django.db.migrations.autodetector import MigrationAutodetector
            from django.db.migrations.state import ProjectState
            loader=MigrationLoader(None)
            if loader.detect_conflicts(): raise RuntimeError('Migration graph conflicts.')
            target=('dic','0033_launch_completion')
            migration=loader.get_migration(*target)
            expected={'academicclass','academicassignment','campannouncement','contactenquiry','foundationdonation'}
            if len(migration.operations)!=5 or any(not isinstance(op,CreateModel) for op in migration.operations):
                raise RuntimeError('Launch migration must contain only five CreateModel operations.')
            before=loader.project_state(('dic','0032_phase4_timetables'))
            after=loader.project_state(target)
            if {name for app,name in set(after.models)-set(before.models)}!=expected:
                raise RuntimeError('Unexpected added models.')
            if any(after.models.get(key)!=value for key,value in before.models.items()):
                raise RuntimeError('Existing model state changed.')
            actual=ProjectState.from_apps(apps)
            if MigrationAutodetector(loader.project_state(),actual).changes(graph=loader.graph):
                raise RuntimeError('Source model/migration drift.')
            call_command('check',databases=[],verbosity=0)
            print('PASS: source graph, model parity, five additive tables and unchanged existing model states.')
            print('PASS: Django system checks (database connections blocked). No unit/integration tests rerun.')
            print('NOT RUN: database applied state, SQL execution, migration application, import/publication.')
            return 0
    except Exception:
        print('FAIL: source migration review could not complete; raw configuration/diagnostics suppressed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
