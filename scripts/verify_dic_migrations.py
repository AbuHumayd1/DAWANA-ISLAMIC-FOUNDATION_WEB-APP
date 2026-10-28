"""Read-only demo migration inventory using the controlled release manifest format.

Never uses the default application database, applies schema, or grants access.
"""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,choices=('dic_2026_demo',))
    args=parser.parse_args()
    # Explicit isolation precedes Django/application imports and dotenv defaults.
    os.environ.update(DATABASE_URL='',DB_NAME=args.database,
        DB_TEST_NAME='test_dic_migration_inspection_unused',
        DJANGO_SETTINGS_MODULE='config.settings.development')
    spec=importlib.util.spec_from_file_location('migration_inspection_isolation',ROOT/'scripts/validate_dic_finance.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    credentials=helper.configure(args.database,readonly=True)
    with ExitStack() as stack:
        helper.guards(stack,credentials)
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        from config.release_migrations import plan_manifest
        if set(settings.DATABASES)!={'default'} or settings.DATABASES['default']['NAME']!=args.database:
            raise RuntimeError('Configured demo identity mismatch.')
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('transaction_read_only')")
            actual,readonly=cursor.fetchone()
        if isinstance(actual,bytes):actual=actual.decode('utf-8')
        if isinstance(readonly,bytes):readonly=readonly.decode('utf-8')
        if actual!=args.database or readonly!='on':
            raise RuntimeError('PostgreSQL demo identity/read-only guard failed.')
        executor=MigrationExecutor(connection)
        loader=executor.loader
        loader.check_consistent_history(connection)
        if loader.detect_conflicts():raise RuntimeError('Migration graph conflicts; stop for review.')
        plan=executor.migration_plan(loader.graph.leaf_nodes())
        manifest=plan_manifest(loader,plan,args.database,settings.SETTINGS_MODULE)
        applied=[dict(app=app,name=name) for app,name in sorted(loader.applied_migrations)]
        receipt=dict(identity=dict(database=actual,host=settings.DATABASES['default']['HOST'],
            port=str(settings.DATABASES['default']['PORT']),transaction_read_only=True),
            manifest=manifest,applied=applied,
            pending=[dict(app=m.app_label,name=m.name) for m,_ in plan],
            purpose='Read-only demo review; not production approval',database_writes=False)
        output=ROOT/'output'/'acceptance';output.mkdir(parents=True,exist_ok=True)
        path=output/('migration-verification-'+uuid.uuid4().hex+'.json')
        with path.open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2)
        print('PASS: dic_2026_demo identity, enforced read-only connection and migration history/graph.')
        print('Applied migrations: '+str(len(applied)))
        for migration,_ in plan:print('PENDING: '+migration.app_label+'.'+migration.name)
        print('Manifest receipt: '+str(path))
        print('No migrations applied. Production migration state remains UNVERIFIED.')


if __name__=='__main__':
    main()
