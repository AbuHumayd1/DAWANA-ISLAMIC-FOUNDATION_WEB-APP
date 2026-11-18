"""Synthetic-only contracts plus real populated PostgreSQL migration recovery."""
import base64
import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, MagicMock, patch

from django.test import SimpleTestCase, TransactionTestCase
from config import integrated_schema_recovery as recovery
from config.deployment_schema_guard import readiness


class RecoveryContracts(SimpleTestCase):
    def setUp(self):
        self.expected = dict(database='synthetic_live', host='db.example.test', port='5432',
                             role='synthetic_owner', cluster_id='1234')
        self.env = dict(RENDER='true', RENDER_GIT_COMMIT='a'*40, DAWANA_0042_MODE='inspect',
                        **{'DAWANA_SCHEMA_'+k.upper(): v for k, v in self.expected.items()})

    def test_explicit_render_mode_revision_and_identity_are_required(self):
        self.assertEqual(recovery.environment(self.env)[0], 'inspect')
        for key in ('RENDER', 'RENDER_GIT_COMMIT', 'DAWANA_0042_MODE', 'DAWANA_SCHEMA_CLUSTER_ID',
                    'DAWANA_SCHEMA_ROLE', 'DAWANA_SCHEMA_HOST', 'DAWANA_SCHEMA_DATABASE'):
            with self.subTest(key=key), self.assertRaises(recovery.Stop):
                recovery.environment({k:v for k,v in self.env.items() if k != key})

    def test_approval_transport_is_explicit_digest_bound_and_release_bound(self):
        raw=json.dumps({'release_commit':'a'*40}).encode()
        env={**self.env, 'DAWANA_0042_MODE':'apply', 'DAWANA_0042_APPROVAL_B64':base64.b64encode(raw).decode(),
             'DAWANA_0042_APPROVAL_SHA256':hashlib.sha256(raw).hexdigest()}
        self.assertEqual(recovery.environment(env)[0], 'apply')
        for key in ('DAWANA_0042_APPROVAL_B64','DAWANA_0042_APPROVAL_SHA256','RENDER_GIT_COMMIT'):
            with self.subTest(key=key), self.assertRaises(recovery.Stop):
                recovery.environment({**env,key:'b'*40})

    def test_owner_backup_fingerprint_and_manifest_approval_are_all_required(self):
        manifest={'release_commit':'a'*40,'plan_sha256':'b'*64}
        approval=dict(manifest=manifest, release_commit='a'*40, reviewed_plan_sha256='b'*64,
                      owner_authorized=True, backup_restore_verified=True,
                      approved_by='Owner',approved_at='2026-11-16T12:00:00Z',
                      backup_reference='verified snapshot',restore_procedure='reviewed restore',
                      rollback_decision='retain additive schema')
        recovery.approve(manifest,approval)
        for key in approval:
            with self.subTest(key=key),self.assertRaises(recovery.Stop):
                recovery.approve(manifest,{k:v for k,v in approval.items() if k!=key})
        with self.assertRaises(recovery.Stop):
            recovery.approve({**manifest,'plan_sha256':'c'*64},approval)

    def test_real_0042_hash_operations_and_dependency_are_pinned(self):
        from django.db.migrations.loader import MigrationLoader
        loader=MigrationLoader(None)
        target=loader.graph.nodes[recovery.TARGET]
        executor=Mock(loader=loader)
        executor.migration_plan.return_value=[]
        with patch.object(loader,'check_consistent_history'):
            recovery.graph(executor)
            with patch.object(recovery,'source_hash',return_value='wrong'),self.assertRaises(recovery.Stop):
                recovery.graph(executor)
            with patch.object(target,'operations',[]),self.assertRaises(recovery.Stop):
                recovery.graph(executor)
        self.assertEqual(len(target.operations),23)
        self.assertIn(('dic','0041_phase_a_order_lifecycle'),target.dependencies)

    def test_tls_endpoint_and_ca_are_checked_before_connecting(self):
        from config.phase_a_migration_build import check_config
        with tempfile.TemporaryDirectory() as folder:
            ca=Path(folder)/'ca.pem';ca.write_text('synthetic; no TLS connection')
            config=dict(ENGINE='django.db.backends.postgresql',NAME=self.expected['database'],
                        HOST=self.expected['host'],PORT='5432',USER=self.expected['role'],
                        OPTIONS={'sslmode':'verify-full','sslrootcert':str(ca)})
            check_config(config,self.expected)
            for mode in ('disable','require','verify-ca'):
                broken=copy.deepcopy(config);broken['OPTIONS']['sslmode']=mode
                connection=Mock(settings_dict=broken)
                with self.assertRaises(recovery.Stop):
                    readiness(connection,Mock(),Mock(),self.expected,'a'*40)
                connection.cursor.assert_not_called()
            for key in ('NAME','HOST','PORT','USER'):
                broken={**config,key:'wrong'}
                with self.assertRaises(Exception):check_config(broken,self.expected)
            config['OPTIONS']['hostaddr']='127.0.0.1'
            with self.assertRaises(Exception):check_config(config,self.expected)

    def test_connected_identity_tls_and_search_path_are_checked(self):
        for values in ((('wrong','synthetic_owner','1234'),),
                       ((self.expected['database'],self.expected['role'],'9999'),),
                       ((self.expected['database'],self.expected['role'],'1234'),(False,)),
                       ((self.expected['database'],self.expected['role'],'1234'),(True,),('unsafe',))):
            connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.side_effect=values
            with patch.object(recovery,'check_config'),self.assertRaises(recovery.Stop):
                recovery.identity(connection,self.expected)

    def test_exception_logs_never_print_driver_messages_or_secrets(self):
        import io
        from django.conf import settings
        output=io.StringIO()
        with (patch.dict('os.environ',self.env,clear=True), patch('django.setup',side_effect=RuntimeError('secret-password')),
              patch.object(settings,'DATABASES',copy.deepcopy(settings.DATABASES)), patch('sys.stderr',output)):
            self.assertEqual(recovery.run(),1)
        self.assertNotIn('secret-password',output.getvalue())

    def test_busy_lock_stops_before_inspection_or_migration(self):
        connection=MagicMock();connection.alias='default'
        cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value=(False,)
        factory=Mock()
        with patch.object(recovery,'check_config'),self.assertRaises(recovery.Stop):
            recovery.execute(connection,MagicMock(),factory,'inspect',self.expected,'a'*40)
        cursor.execute.assert_any_call('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        factory.assert_not_called()

    def test_partial_index_predicates_are_not_accepted_by_name_alone(self):
        self.assertTrue(recovery.expected_predicate('dic_house_canonical_unique',"(NOT ((canonical_key)::text = ''::text))"))
        self.assertFalse(recovery.expected_predicate('dic_house_canonical_unique',"canonical_key='unrelated'"))
        self.assertFalse(recovery.expected_predicate('dic_food_date_meal_unique',"meal<>''"))

    def test_graph_conflicts_inconsistent_history_and_unknown_recorder_stop(self):
        from django.db.migrations.loader import MigrationLoader
        loader=MigrationLoader(None);executor=Mock(loader=loader)
        with patch.object(loader,'check_consistent_history'),patch.object(loader,'detect_conflicts',return_value={'dic':['bad']}):
            with self.assertRaises(recovery.Stop):recovery.graph(executor)
        with patch.object(loader,'check_consistent_history',side_effect=RuntimeError('inconsistent')):
            with self.assertRaises(RuntimeError):recovery.graph(executor)
        with patch.object(loader,'check_consistent_history'),patch.object(loader,'applied_migrations',{('unknown','0001'):True}):
            with self.assertRaises(recovery.Stop):recovery.graph(executor)


class PopulatedRecovery(TransactionTestCase):
    """Never allowed on a live database. Apply/reverse only inside disposable tests."""
    def setUp(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        if connection.vendor!='postgresql' or not connection.settings_dict['NAME'].startswith('test_'):
            raise RuntimeError('Disposable PostgreSQL required; no production or SQLite fallback.')
        self.connection=connection;self.factory=MigrationExecutor
        self.expected=dict(database=connection.settings_dict['NAME'],host='synthetic.test',port='5432',
                           role='synthetic',cluster_id='synthetic')
        self.commit='a'*40
        # Test-only local transport; production TLS/identity are separately tested above.
        self.patches=[patch.object(recovery,'check_config'),patch.object(recovery,'identity',return_value=self.expected),
                      patch('config.deployment_schema_guard.check_config'),
                      patch('config.deployment_schema_guard.identity',return_value=self.expected)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.factory(connection).migrate([('dic','0041_phase_a_order_lifecycle')])
        self.addCleanup(self.restore)

    def restore(self):
        self.factory(self.connection).migrate([recovery.TARGET])

    def run_recovery(self,mode='inspect',approval=None):
        from django.db import transaction
        return recovery.execute(self.connection,transaction,self.factory,mode,self.expected,self.commit,approval)

    def approval(self,manifest):
        return dict(manifest=manifest,release_commit=self.commit,reviewed_plan_sha256=manifest['plan_sha256'],
                    owner_authorized=True,backup_restore_verified=True,approved_by='Synthetic Owner',
                    approved_at='2026-11-16T12:00:00Z',backup_reference='synthetic snapshot',
                    restore_procedure='synthetic restore verified',rollback_decision='retain additive schema')

    def test_missing_inspection_sqlstate_apply_and_idempotent_retry_preserve_populated_rows(self):
        from django.db import transaction
        from dic.test_participant_portal import PortalFixtures
        # Create realistic registrations/payments before schema downgrade using shared fixtures.
        self.restore()
        fixture=PortalFixtures();fixture.setUp()
        from dic.models import House,HouseAllocation,CampCheckIn
        from dic.participant_services import ensure_enrollment,id_command
        enrollment=ensure_enrollment(fixture.item.pk)
        id_command(enrollment.pk,'issue',fixture.id_manager)
        CampCheckIn.objects.create(participant=fixture.item.participant,edition=fixture.edition,checked_in_by=fixture.id_manager)
        house=House.objects.create(edition=fixture.edition,name='Synthetic preserved house',gender='male',capacity=25)
        HouseAllocation.objects.create(participant=fixture.item.participant,edition=fixture.edition,house=house,allocated_by=fixture.id_manager)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND "
                           "(tablename LIKE 'dic_%' OR tablename LIKE 'accounts_%') ORDER BY tablename")
            tables=[row[0] for row in cursor.fetchall() if row[0] not in
                    ('dic_certificaterelease','dic_lecturerecording','dic_participationcertificate')]
            # Compare unchanged columns on every existing application table.
            snapshots={}
            for table in tables:
                cursor.execute('SELECT * FROM '+self.connection.ops.quote_name(table)+' ORDER BY 1')
                snapshots[table]=([c.name for c in cursor.description],cursor.fetchall())
        self.factory(self.connection).migrate([('dic','0041_phase_a_order_lifecycle')])
        report=self.run_recovery();manifest=report['manifest']
        self.assertEqual(manifest['state'],'missing')
        self.assertEqual([n['name'] for n in manifest['pending']],[recovery.TARGET[1]])
        self.assertEqual(manifest['schema']['zero_row_probes']['dic_house']['sqlstate'],'42703')
        self.assertEqual(manifest['schema']['zero_row_probes']['dic_lecturerecording']['sqlstate'],'42P01')
        with patch('django.db.models.signals.post_migrate.send') as post:
            result=self.run_recovery('apply',self.approval(manifest))
            post.assert_not_called()
        self.assertEqual(result['status'],'COMMITTED_0042')
        self.assertEqual(self.run_recovery('apply',self.approval(manifest))['status'],'ALREADY_APPLIED_NO_WRITES')
        self.assertEqual(self.run_recovery('verify')['status'],'VERIFIED_READ_ONLY')
        with self.connection.cursor() as cursor:
            for table,(columns,rows) in snapshots.items():
                # Only the new metadata columns changed, with safe blank/general defaults.
                cursor.execute('SELECT '+','.join(self.connection.ops.quote_name(c) for c in columns)+
                               ' FROM '+self.connection.ops.quote_name(table)+' ORDER BY 1')
                self.assertEqual(cursor.fetchall(),rows,table)
        # Historical 0042 recovery is intentionally scoped to 0042. The
        # deployment readiness guard instead validates the CURRENT complete
        # ORM schema (including approved 0043–0045 successors). Apply those
        # successors only inside this disposable test database before checking
        # full-release readiness; never relax production's fail-closed guard.
        current = self.factory(self.connection)
        current.migrate(current.loader.graph.leaf_nodes())
        self.assertEqual(readiness(self.connection,transaction,self.factory,self.expected,self.commit)['status'],
                         'DEPLOYMENT_SCHEMA_READY_READ_ONLY')
        from dic.models import House,CampVideo,LectureRecording,ParticipationCertificate,CertificateRelease
        list(House.objects.all());list(CampVideo.objects.all());list(LectureRecording.objects.all())
        self.assertEqual(ParticipationCertificate.objects.count(),0)
        self.assertEqual(CertificateRelease.objects.count(),0)
        from django.test import Client,override_settings
        from django.urls import reverse
        from dic.test_participant_portal import TEST_DELIVERY
        fixture.assertEqual=self.assertEqual
        with override_settings(**TEST_DELIVERY):
            client,_=fixture.login()
            self.assertEqual(client.get(reverse('dic:participant-enrollments')).status_code,200)
            self.assertEqual(client.get(reverse('dic:operations-participants')).status_code,403)
        fixture.operator.is_staff=True;fixture.operator.save(update_fields=['is_staff'])
        staff=Client();staff.force_login(fixture.operator)
        self.assertEqual(staff.get(reverse('dic:operations-participants'),{'edition':fixture.edition.pk}).status_code,200)

    def test_approval_mismatch_leaves_all_0042_objects_absent(self):
        manifest=self.run_recovery()['manifest']
        for approval in (None,{**self.approval(manifest),'reviewed_plan_sha256':'wrong'},
                         {**self.approval(manifest),'release_commit':'b'*40}):
            with self.assertRaises(recovery.Stop):self.run_recovery('apply',approval)
            self.assertEqual(self.run_recovery()['manifest']['state'],'missing')

    def test_partial_unrecorded_schema_is_not_faked_or_repaired(self):
        with self.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE dic_house ADD COLUMN canonical_key varchar(80) NOT NULL DEFAULT ''")
        try:
            manifest=self.run_recovery()['manifest'];self.assertEqual(manifest['state'],'inconsistent')
            with self.assertRaises(recovery.Stop):self.run_recovery('apply',self.approval(manifest))
        finally:
            with self.connection.cursor() as cursor:cursor.execute('ALTER TABLE dic_house DROP COLUMN canonical_key')

    def test_missing_and_faked_history_block_deployment(self):
        from django.db import transaction
        with self.assertRaises(recovery.Stop):readiness(self.connection,transaction,self.factory,self.expected,self.commit)
        self.restore()
        with self.connection.cursor() as cursor:cursor.execute('ALTER TABLE dic_house DROP COLUMN canonical_key CASCADE')
        try:
            self.assertEqual(self.run_recovery()['manifest']['state'],'inconsistent')
            with self.assertRaises(recovery.Stop):readiness(self.connection,transaction,self.factory,self.expected,self.commit)
        finally:
            # Restore only this test's damaged disposable schema using real migration history.
            with self.connection.cursor() as cursor:
                cursor.execute("ALTER TABLE dic_house ADD COLUMN canonical_key varchar(80) NOT NULL DEFAULT ''")
                cursor.execute("CREATE UNIQUE INDEX dic_house_canonical_unique ON dic_house(edition_id,canonical_key) WHERE canonical_key<>''")

    def test_unexpected_pending_plan_is_rejected_without_applying_anything(self):
        real=self.factory(self.connection)
        unexpected=importlib.import_module('dic.migrations.0041_phase_a_order_lifecycle').Migration('unexpected','dic')
        proxy=Mock(wraps=real);proxy.loader=real.loader;proxy.connection=self.connection
        proxy.migration_plan.return_value=real.migration_plan(real.loader.graph.leaf_nodes())+[(unexpected,False)]
        with patch.object(self,'factory',return_value=proxy),self.assertRaises(recovery.Stop):
            manifest=self.run_recovery()['manifest']
            self.run_recovery('apply',self.approval(manifest))
        self.assertEqual(self.run_recovery()['manifest']['state'],'missing')

    def test_inspection_enforces_read_only_at_the_database(self):
        from django.db import transaction,DatabaseError
        original=recovery.physical
        def checked(connection,loader):
            with connection.cursor() as cursor:
                cursor.execute('SHOW transaction_read_only');self.assertEqual(cursor.fetchone()[0],'on')
            with self.assertRaises(DatabaseError),transaction.atomic(),connection.cursor() as cursor:
                cursor.execute("UPDATE dic_house SET name=name WHERE FALSE")
            return original(connection,loader)
        with patch.object(recovery,'physical',side_effect=checked):self.run_recovery()

    def test_constraints_conflicts_are_reported_and_not_silently_deleted(self):
        self.restore()
        from dic.models import CampEdition,House
        from datetime import date
        edition=CampEdition.objects.create(name='Synthetic',year=2026,camp_start_date=date(2026,12,23),camp_end_date=date(2027,1,1))
        with self.connection.cursor() as cursor:cursor.execute('DROP INDEX dic_house_canonical_unique')
        try:
            House.objects.create(edition=edition,name='One',gender='male',canonical_key='same')
            House.objects.create(edition=edition,name='Two',gender='male',canonical_key='same')
            manifest=self.run_recovery()['manifest']
            self.assertEqual(manifest['schema']['unique_conflicts']['dic_house'],1)
            self.assertEqual(manifest['state'],'inconsistent')
            with self.assertRaises(recovery.Stop):self.run_recovery('apply',self.approval(manifest))
            self.assertEqual(House.objects.filter(edition=edition).count(),2)
        finally:
            # Disposable fixtures only; never part of production recovery code.
            House.objects.filter(edition=edition).delete()
            with self.connection.cursor() as cursor:
                cursor.execute("CREATE UNIQUE INDEX dic_house_canonical_unique ON dic_house(edition_id,canonical_key) WHERE canonical_key<>''")

    def test_ddl_and_recorder_roll_back_together_on_verification_failure(self):
        manifest=self.run_recovery()['manifest'];original=recovery.inspect
        def fail_after(connection,executor,*args):
            result=original(connection,executor,*args)
            if recovery.TARGET in executor.loader.applied_migrations:raise recovery.Stop('SYNTHETIC_VERIFY_FAILURE')
            return result
        with patch.object(recovery,'inspect',side_effect=fail_after),self.assertRaises(recovery.Stop):
            self.run_recovery('apply',self.approval(manifest))
        self.assertEqual(self.run_recovery()['manifest']['state'],'missing')
