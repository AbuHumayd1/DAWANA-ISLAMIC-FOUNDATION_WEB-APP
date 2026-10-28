"""Database-free release contracts; never apply migration plans or grants."""
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace as NS
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory,force_authenticate
from config.release_security import validate_production
from config.release_migrations import validate_approval,digest,plan_manifest
from .management.commands.setup_dic_staff_roles import Command
from .operations_api import OperationsParticipantListView,OperationsRegistrationListView,OperationsDashboardView,OperationsReportView
from dic_finance.services import financial_totals


class ReleaseReadinessTests(SimpleTestCase):
    def config(self):
        return dict(DEBUG=False,SECRET_KEY='synthetic-'+('x'*60),ALLOWED_HOSTS=['backend.example.test'],
            CORS_ALLOWED_ORIGINS=['https://portal.example.test'],CSRF_TRUSTED_ORIGINS=['https://portal.example.test'],
            SECURE_SSL_REDIRECT=True,SESSION_COOKIE_SECURE=True,CSRF_COOKIE_SECURE=True,
            PAYSTACK_MODE='test',PAYSTACK_SECRET_KEY='sk_test_synthetic',
            DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','OPTIONS':{'sslmode':'require'}}},
            PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'],
            CACHES={'default':{'BACKEND':'django.core.cache.backends.db.DatabaseCache'}})

    def test_strict_production_configuration(self):
        validate_production(self.config())
        for key,value in [('DEBUG',True),('SECRET_KEY','short'),('ALLOWED_HOSTS',['*']),
                ('CSRF_TRUSTED_ORIGINS',[]),('CORS_ALLOWED_ORIGINS',['http://portal.example.test']),
                ('PAYSTACK_MODE','live'),('PAYSTACK_SECRET_KEY','sk_live_synthetic'),
                ('SESSION_COOKIE_SECURE',False),('PASSWORD_HASHERS',['django.contrib.auth.hashers.MD5PasswordHasher']),
                ('CACHES',{'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}})]:
            with self.subTest(key=key),self.assertRaises(ImproperlyConfigured):validate_production({**self.config(),key:value})

    def test_exact_migration_approval_requires_backup_and_rollback(self):
        manifest={'database':'release_synthetic','steps':[{'app':'dic','name':'0027_feedback_welfare'}]}
        approval=dict(manifest=deepcopy(manifest),approved_by='Synthetic approver',approved_at='2026-10-28',
            backup_reference='synthetic backup',restore_procedure='synthetic restore',rollback_decision='restore before traffic')
        validate_approval(manifest,approval)
        for key in ('approved_by','backup_reference','restore_procedure','rollback_decision'):
            with self.subTest(key=key),self.assertRaises(RuntimeError):validate_approval(manifest,{**approval,key:''})
        changed=deepcopy(manifest);changed['steps'].append({'app':'dic','name':'0031_phase5_feedback_welfare'})
        with self.assertRaises(RuntimeError):validate_approval(changed,approval)
        self.assertNotEqual(digest(manifest),digest(changed))
        for invalid in (None,[], 'approval'):
            with self.assertRaises(RuntimeError):validate_approval(manifest,invalid)

    def test_staff_role_default_is_preview_only_without_database_calls(self):
        with patch('dic.management.commands.setup_dic_staff_roles.Group.objects') as groups:
            command=Command(stdout=StringIO());command.handle(apply_reviewed_grants=False)
            self.assertEqual(groups.mock_calls,[])
        grants=Command.GROUP_PERMISSIONS['DIC Administrators']
        self.assertNotIn('can_view_dic_finance',grants);self.assertNotIn('view_participant',grants)
        self.assertNotIn('can_view_dic_welfare',grants)

    def test_migration_manifest_rejects_backward_steps_and_records_ordering(self):
        class SyntheticMigration:
            app_label='dic'
            name='synthetic_only'
            dependencies=[('dic','0026_house_score_transaction')]
            run_before=[('dic','0027_feedback_welfare')]
        # This module's real source file supplies a stable fixture hash; no ORM.
        migration=SyntheticMigration()
        manifest=plan_manifest(None,[(migration,False)],'synthetic-release','source-only')
        self.assertEqual(manifest['steps'][0]['run_before'],[['dic','0027_feedback_welfare']])
        self.assertEqual(len(manifest['steps'][0]['source_sha256']),64)
        with self.assertRaises(RuntimeError):plan_manifest(None,[(migration,True)],'synthetic-release','source-only')

    def test_general_operations_cannot_read_identifiable_records(self):
        actor=NS(is_authenticated=True,is_active=True,is_staff=True,is_superuser=False,
            has_perm=lambda key:key=='dic.can_view_dic_operations')
        for view in (OperationsParticipantListView,OperationsRegistrationListView,OperationsDashboardView):
            request=APIRequestFactory().get('/?edition=1');force_authenticate(request,user=actor)
            self.assertEqual(view.as_view()(request).status_code,403)

    def test_export_permission_alone_does_not_export_personal_records(self):
        actor=NS(is_authenticated=True,is_active=True,is_staff=True,is_superuser=False,
            has_perm=lambda key:key in ('dic.can_view_dic_operations','dic.can_export_dic_reports'))
        for report in ('participants','registrations','houses'):
            request=APIRequestFactory().get('/?report='+report+'&edition=1');force_authenticate(request,user=actor)
            with patch('dic.operations_api._edition_from_request',return_value=NS(pk=1)):
                self.assertEqual(OperationsReportView.as_view()(request).status_code,403)

    def test_financial_cash_commitments_and_budget_remain_distinct(self):
        payments=[dict(verified_kobo=7500,gross_verified_kobo=10000,adjustment_kobo=2500,status='successful',exception='')]
        records=[dict(kind='expense',status='approved',amount_kobo=900),dict(kind='expense',status='paid',amount_kobo=500)]
        result=financial_totals(payments,records,[dict(amount_kobo=5000)],500)
        self.assertEqual(result['gross_verified_collections_kobo'],10000)
        self.assertEqual(result['recorded_adjustments_kobo'],2500)
        self.assertEqual(result['net_verified_collections_kobo'],7500)
        self.assertEqual(result['expenditure_kobo'],500);self.assertEqual(result['approved_unpaid_kobo'],900)
        self.assertEqual(result['net_position_kobo'],7000);self.assertIsNone(result['available_operating_balance_kobo'])
