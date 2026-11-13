"""Database-free reporting contracts, permissions and evidence regressions."""
from datetime import date, datetime
from types import SimpleNamespace as NS
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException
from rest_framework.test import APIRequestFactory, force_authenticate
from . import reporting_services as reports
from .reporting_api import ReportingView, export_rows, drilldowns
from .operations_exports import spreadsheet_safe


BASE={'dic.can_view_dic_operations','dic.can_export_dic_reports'}


class ReportingPolicyTests(SimpleTestCase):
    def actor(self,*permissions,**changes):
        values=dict(pk=1,is_authenticated=True,is_active=True,is_staff=True,is_superuser=False,
            has_perm=lambda key:key in BASE|set(permissions))
        values.update(changes);return NS(**values)

    def selected(self,domain='registration',**changes):
        return reports.filters(changes,domain)

    def test_domain_permissions_are_independent_of_general_reporting(self):
        general=self.actor()
        for domain in ('overview','registration','academic'):reports.require_report(general,domain)
        for domain in ('finance','accommodation','attendance','feedback','welfare'):
            with self.subTest(domain=domain),self.assertRaises(PermissionDenied):reports.require_report(general,domain)
        self.assertEqual({row['id'] for row in reports.capabilities(general)},{'overview','registration','academic'})

    def test_inactive_nonstaff_and_unauthenticated_staff_are_denied(self):
        for changes in ({'is_active':False},{'is_staff':False},{'is_authenticated':False}):
            with self.assertRaises(PermissionDenied):reports.require_report(self.actor(**changes),'overview')

    def test_finance_feedback_and_welfare_permissions_do_not_imply_each_other(self):
        for permission,allowed,denied in [('dic.can_view_dic_finance','finance','welfare'),
                ('dic.can_view_dic_feedback','feedback','welfare'),('dic.can_view_dic_welfare','welfare','finance')]:
            actor=self.actor(permission);reports.require_report(actor,allowed)
            with self.assertRaises(PermissionDenied):reports.require_report(actor,denied)

    def test_api_denies_restricted_domains_before_edition_or_report_queries(self):
        for domain in ('finance','welfare','attendance','feedback'):
            request=APIRequestFactory().get('/?edition=1&domain='+domain)
            force_authenticate(request,user=self.actor())
            with patch('dic.reporting_api.CampEdition.objects') as editions,patch('dic.reporting_services.report') as report:
                self.assertEqual(ReportingView.as_view()(request).status_code,403)
                editions.filter.assert_not_called();report.assert_not_called()

    def test_api_requires_explicit_edition_without_fallback(self):
        request=APIRequestFactory().get('/?domain=registration');force_authenticate(request,user=self.actor())
        with patch('dic.reporting_api.CampEdition.objects') as editions:
            self.assertEqual(ReportingView.as_view()(request).status_code,400);editions.filter.assert_not_called()

    def test_category_from_another_edition_is_rejected(self):
        request=APIRequestFactory().get('/?edition=1&domain=registration&category=2');force_authenticate(request,user=self.actor())
        with patch('dic.reporting_api.CampEdition.objects') as editions,patch('dic.reporting_api.RegistrationCategory.objects') as categories,patch('dic.reporting_services.report') as report:
            edition=NS(pk=1);editions.filter.return_value.first.return_value=edition
            categories.filter.return_value.exists.return_value=False
            self.assertEqual(ReportingView.as_view()(request).status_code,400)
            categories.filter.assert_called_once_with(pk='2',edition=edition);report.assert_not_called()

    def test_finance_export_needs_detail_and_export_permissions(self):
        request=APIRequestFactory().get('/?edition=1&domain=finance&export=csv');force_authenticate(request,user=self.actor('dic.can_view_dic_finance'))
        with patch('dic.reporting_api.CampEdition.objects') as editions,patch('dic.reporting_services.report') as report:
            editions.filter.return_value.first.return_value=NS(pk=1)
            self.assertEqual(ReportingView.as_view()(request).status_code,403);report.assert_not_called()

    def test_date_sort_page_and_status_validation(self):
        for changes in ({'date_from':'not-a-date'},{'date_from':'2026-12-26','date_to':'2026-12-25'},
                {'category':'0'},{'page':'0'},{'sort':'password'},{'status':'successful'},{'q':'x'*101}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.selected(**changes)
        self.assertEqual(self.selected('finance',status='successful')['status'],'successful')

    def test_anonymous_feedback_cannot_be_filtered_by_camper_category(self):
        with self.assertRaises(ValidationError):self.selected('feedback',category='1')

    def test_lagos_date_boundaries_use_exclusive_next_midnight(self):
        query=MagicMock();query.filter.return_value=query
        reports.period(query,'created_at',self.selected(date_from='2026-12-25',date_to='2026-12-25'))
        first,last=query.filter.call_args_list
        self.assertEqual(first.kwargs['created_at__gte'],datetime(2026,12,25,tzinfo=reports.TZ))
        self.assertEqual(last.kwargs['created_at__lt'],datetime(2026,12,26,tzinfo=reports.TZ))

    def test_registration_queries_are_scoped_to_edition_and_category(self):
        edition=NS(pk=7)
        with patch('dic.reporting_services.RegistrationOrderItem.objects') as items:
            query=items.filter.return_value;query.filter.return_value=query
            reports.scoped_items(edition,self.selected(category='3'),registration_dates=False)
            items.filter.assert_called_once_with(order__edition=edition,category__edition=edition)
            query.filter.assert_called_once_with(category_id='3')

    def test_financial_fold_uses_verified_values_not_attempt_amount_or_status(self):
        rows=[dict(gross_verified_kobo=10000,adjustment_kobo=2500,verified_kobo=7500,exception='',status='successful'),
            dict(gross_verified_kobo=0,adjustment_kobo=0,verified_kobo=0,exception='duplicate_receipt',status='successful'),
            dict(gross_verified_kobo=0,adjustment_kobo=0,verified_kobo=0,exception='',status='pending'),
            dict(gross_verified_kobo=0,adjustment_kobo=0,verified_kobo=0,exception='',status='failed')]
        result=reports.financial_fold(rows)
        self.assertEqual((result['gross'],result['refunds'],result['net'],result['successful']),(10000,2500,7500,1))
        self.assertEqual((result['pending'],result['failed'],result['exceptions']),(1,1,1))

    def test_missing_schemas_do_not_become_zero_statistics(self):
        with patch('dic.reporting_services.storage',return_value=False):
            for function in (reports.finance,reports.accommodation,reports.attendance):
                result=function(NS(pk=1),self.selected(),self.actor())
                self.assertFalse(result['available']);self.assertEqual(result['metrics'],[])
        error=APIException('pending');error.status_code=503
        with patch('dic.feedback_services.require_feedback_storage',side_effect=error):
            for function in (reports.feedback,reports.welfare):
                self.assertFalse(function(NS(pk=1),self.selected(),self.actor())['available'])

    def test_academic_not_configured_never_uses_registration_or_house_as_class(self):
        result=reports.report(NS(pk=1),self.selected(),self.actor(),'academic')
        self.assertEqual(result['state'],'Not Yet Configured');self.assertEqual(result['rows'],[])

    def test_unknown_scan_is_not_confirmed_absence_and_invalid_transitions_are_flagged(self):
        self.assertEqual(reports.movement_findings(False,[]),('unknown',0))
        self.assertEqual(reports.movement_findings(True,[{'kind':'departure'}]),('outside',0))
        self.assertEqual(reports.movement_findings(True,[{'kind':'return'}]),('inside',1))
        self.assertEqual(reports.movement_findings(False,[{'kind':'departure'}]),('outside',1))

    def test_pagination_sorting_and_export_share_full_filtered_rows(self):
        data=dict(metrics=[],series={},rows=[dict(label=str(index),value=index) for index in range(65)])
        selected=self.selected(sort='-value',page='2')
        page=reports.page_result(data,selected)
        self.assertEqual(page['count'],65);self.assertEqual(page['rows'][0]['value'],14)
        self.assertEqual(len(reports.page_result(data,selected,exporting=True)['rows']),65)

    def test_csv_and_print_projection_preserves_unknowns_and_formula_safety(self):
        columns,rows=export_rows(dict(metrics=[reports.metric('Unknown',None)],series={'Suppressed':[dict(label='Group',value=None)]},rows=[dict(label='=formula',value=1)]))
        self.assertIn('Unavailable / privacy threshold',str(rows));self.assertEqual(columns[:2],['Section','Description'])
        self.assertTrue(spreadsheet_safe(rows[-1][1]).startswith("'"))

    def test_feedback_versions_averages_and_suppression_are_preserved(self):
        groups=[dict(channel='daily',day='2026-12-25',questionnaire_version=version,count=5,suppressed=False,
            questions={'ratings':{'learning':'Learning'}},distributions={'learning':{'1':0,'2':0,'3':5,**({'4':0,'5':0} if version==2 else {})}},
            scale=[(n,str(n)) for n in range(1,4 if version==1 else 6)]) for version in (1,2)]
        groups.append(dict(channel='daily',day='2026-12-26',questionnaire_version=2,count=None,suppressed=True))
        with patch('dic.feedback_services.require_feedback_storage'),patch('dic.feedback_services.feedback_summary',return_value=groups),patch('dic.reporting_services.registered_cohort_dates',return_value=[date(2026,12,23)]*10):
            result=reports.feedback(NS(pk=1),self.selected('feedback'),self.actor())
        self.assertEqual({row['scale_max'] for row in result['rows'] if 'scale_max' in row},{3,5})
        self.assertIsNone(result['series']['Responses by channel, version and camp day'][-1]['value'])
        self.assertTrue(all('responses' not in row for row in result['rows']))

    def test_participation_uses_distinct_registered_cohort_not_attempts_or_assumed_eligibility(self):
        self.assertEqual(reports.cohort_participation(5,[date(2026,12,23)]*10,'2026-12-25'),(10,50.0))
        self.assertEqual(reports.cohort_participation(5,[],'2026-12-25'),(0,None))
        self.assertEqual(reports.cohort_participation(6,[date(2026,12,23)]*5,'2026-12-25'),(5,None))

    def test_drilldowns_do_not_grant_detail_permissions(self):
        self.assertEqual(drilldowns(self.actor(),'finance',1),[])
        self.assertEqual(drilldowns(self.actor(),'welfare',1),[])
        self.assertEqual(len(drilldowns(self.actor('dic.can_view_dic_welfare'),'welfare',1)),1)

    def test_welfare_statistics_never_project_case_descriptions_or_identifiers(self):
        selected=self.selected('welfare')
        with patch('dic.feedback_services.require_feedback_storage'),patch('dic.reporting_services.WelfareReport.objects') as cases,patch('dic.reporting_services.WelfareEvent.objects') as events,patch('dic.reporting_services.grouped',return_value=[dict(label='new',value=2)]):
            query=cases.filter.return_value;query.count.return_value=2;query.filter.return_value=query
            events.filter.return_value.order_by.return_value.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value=[]
            result=reports.welfare(NS(pk=1),selected,self.actor('dic.can_view_dic_welfare'))
        self.assertTrue(result['available'])
        self.assertEqual(set(result['rows'][0]),{'label','status','value'})
        for point in result['series'].values():
            for row in point:self.assertLessEqual(set(row),{'label','value'})
