"""Explicit demo-only Phase 5 schema gate and rollback-only integration runner.

No action runs on import. Never creates, flushes, resets or destroys databases.
"""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
TARGET=('dic','0031_phase5_feedback_welfare')


def require(condition,message):
    if not condition: raise RuntimeError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('preflight','migrate','integration'))
    parser.add_argument('--database',required=True,choices=('dic_2026_demo',))
    parser.add_argument('--confirm-demo-writes',action='store_true')
    parser.add_argument('--approve-phase5-schema',action='store_true')
    args=parser.parse_args()
    require(args.command=='preflight' or args.confirm_demo_writes,'Explicit demo writes confirmation is required.')
    require(args.command!='migrate' or args.approve_phase5_schema,'Separate Phase 5 schema approval is required.')
    # Set the explicit target before Django or environment files are imported.
    os.environ.update(DATABASE_URL='',DB_NAME=args.database,DB_TEST_NAME='test_dic_phase5_unused',
        DJANGO_SETTINGS_MODULE='config.settings.development',DIC_PORTAL_ACCOUNTS_ENABLED='False',
        DIC_GOOGLE_CLIENT_ID='',DIC_GOOGLE_CLIENT_SECRET='',DIC_GOOGLE_REDIRECT_URI='')
    spec=importlib.util.spec_from_file_location('phase5_demo_isolation',ROOT/'scripts/validate_dic_finance.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    credentials=helper.configure(args.database,readonly=args.command=='preflight')
    with ExitStack() as stack:
        helper.guards(stack,credentials)
        from django.conf import settings
        from django.db import connection, transaction
        from django.db.migrations.executor import MigrationExecutor
        from django.core.management import call_command
        from django.test import TestCase
        from django.test.runner import iter_test_cases
        from dic.models import (AnonymousCamperResponse,CamperFeedbackReceipt,IdentifiedFeedback,
            LecturerFeedbackAccess,WelfareReport,WelfareEvent)
        require(set(settings.DATABASES)=={'default'},'Unexpected database aliases.')
        require(settings.DATABASES['default']['NAME']==args.database=='dic_2026_demo','Configured database mismatch.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            actual=cursor.fetchone()[0]
        if isinstance(actual,bytes):actual=actual.decode('utf-8')
        require(actual==args.database=='dic_2026_demo','PostgreSQL identity mismatch.')
        executor=MigrationExecutor(connection)
        require(not executor.loader.detect_conflicts(),'Migration graph conflicts.')
        require(('dic','0030_portal_account_authentication') in executor.loader.applied_migrations,'Phase 3 schema must already be present.')
        plan=executor.migration_plan([TARGET])
        require(all(not backwards and (migration.app_label,migration.name) in
            {('dic','0027_feedback_welfare'),TARGET} for migration,backwards in plan),
            'Unexpected pending dependency; stop for review.')
        print('Database identity: dic_2026_demo. Pending approved targets: '+', '.join(m.name for m,_ in plan))
        if args.command=='preflight': return
        if args.command=='migrate':
            # Explicit target only; Django's migration executor retains its normal
            # transactional schema behavior. No seed or permission grants to users.
            call_command('migrate',TARGET[0],TARGET[1],interactive=False,verbosity=1)
            return
        require(not plan,'Phase 5 schema must be approved/applied before integration.')
        from dic.feedback_services import require_feedback_storage
        require_feedback_storage()
        models=(AnonymousCamperResponse,CamperFeedbackReceipt,IdentifiedFeedback,LecturerFeedbackAccess,WelfareReport,WelfareEvent)
        before={model._meta.label:model.objects.count() for model in models}
        suite=unittest.defaultTestLoader.loadTestsFromNames(['dic.test_feedback.FeedbackIntegrationTests'])
        require(all(isinstance(case,TestCase) for case in iter_test_cases(suite)),'Unexpected integration manifest.')
        # No DiscoverRunner: no database creation, migration, flush or teardown.
        with transaction.atomic():
            result=unittest.TextTestRunner(verbosity=2).run(suite)
            transaction.set_rollback(True)
        after={model._meta.label:model.objects.count() for model in models}
        require(before==after,'Rollback verification failed; preserve evidence and investigate.')
        output=ROOT/'output'/'acceptance';output.mkdir(parents=True,exist_ok=True)
        receipt=output/('phase5-'+uuid.uuid4().hex+'.json')
        receipt.write_text(json.dumps(dict(database=args.database,tests=result.testsRun,
            successful=result.wasSuccessful() and not result.skipped,cleanup='transaction_rollback',
            feedback_welfare_counts_unchanged=before==after)),encoding='utf-8')
        require(result.wasSuccessful() and not result.skipped,'Integration failed; see synthetic test diagnostics.')


if __name__=='__main__':
    main()
