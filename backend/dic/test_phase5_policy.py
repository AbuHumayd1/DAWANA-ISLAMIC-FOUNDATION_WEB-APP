"""Database-free Phase 5 authorization and historical interpretation tests."""
from datetime import date, timedelta, datetime, timezone as datetime_timezone
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.test import APIRequestFactory
from .feedback_schema import QUESTIONS, RATINGS, questionnaire
from .feedback_services import validate_response, camp_today, feedback_summary, portal_item
from .feedback_api import CamperWelfareSubmitView


class Phase5PolicyTests(SimpleTestCase):
    def setUp(self):
        self.today=date(2026,12,25)
        self.edition=NS(camp_start_date=date(2026,12,23),camp_end_date=date(2027,1,1))

    def payload(self,kind='daily',tutor=False):
        data=dict(channel=kind,day=str(self.today),ratings={key:5 for key in questionnaire(kind,tutor)['ratings']},answers={})
        if kind=='final': data.update(day=str(self.edition.camp_end_date),recommend=True)
        return data

    def test_daily_same_day_and_five_point_bounds(self):
        with patch('dic.feedback_services.camp_today',return_value=self.today):
            self.assertEqual(validate_response(self.payload(),self.edition,('daily',))['ratings']['learning'],5)
            for day in (self.today-timedelta(days=1),self.today+timedelta(days=1)):
                with self.assertRaises(ValidationError):validate_response({**self.payload(),'day':str(day)},self.edition,('daily',))
            for value in (0,6):
                with self.assertRaises(ValidationError):validate_response({**self.payload(),'ratings':{key:value for key in QUESTIONS['daily']['ratings']}},self.edition,('daily',))

    def test_final_opens_final_date_and_uses_canonical_day(self):
        with patch('dic.feedback_services.camp_today',return_value=self.today):
            with self.assertRaises(ValidationError):validate_response(self.payload('final'),self.edition,('final',))
        with patch('dic.feedback_services.camp_today',return_value=self.edition.camp_end_date):
            self.assertTrue(validate_response(self.payload('final'),self.edition,('final',))['answers']['recommend'])

    def test_tutor_questions_omit_housing_and_reject_forged_housing_answer(self):
        with patch('dic.feedback_services.camp_today',return_value=self.today):
            self.assertNotIn('comfort',validate_response(self.payload(tutor=True),self.edition,('daily',),tutor=True)['ratings'])
            with self.assertRaises(ValidationError):validate_response(self.payload(),self.edition,('daily',),tutor=True)

    def test_accommodation_can_be_not_applicable_without_skipping_other_questions(self):
        data=self.payload();data['ratings'].pop('comfort')
        with patch('dic.feedback_services.camp_today',return_value=self.today):
            validate_response(data,self.edition,('daily',))
            data['ratings'].pop('learning')
            with self.assertRaises(ValidationError):validate_response(data,self.edition,('daily',))

    def test_camp_timezone_independent_of_active_timezone(self):
        with patch('dic.feedback_services.timezone.now',return_value=datetime(2026,12,24,23,30,tzinfo=datetime_timezone.utc)):
            self.assertEqual(camp_today(),date(2026,12,25))

    def test_historical_and_current_scales_not_combined(self):
        rows=[NS(channel='daily',day=self.today,questionnaire_version=version,ratings={'learning':3},answers={}) for version in (1,2) for _ in range(5)]
        with patch('dic.feedback_services.AnonymousCamperResponse.objects') as anonymous,patch('dic.feedback_services.IdentifiedFeedback.objects') as identified:
            anonymous.filter.return_value=rows;identified.filter.return_value=[]
            result=feedback_summary(NS(pk=1))
        self.assertEqual([len(row['scale']) for row in result],[3,5])
        self.assertEqual(result[1]['scale'],RATINGS)

    def test_version_groups_cannot_combine_to_bypass_privacy_threshold(self):
        rows=[NS(channel='daily',day=self.today,questionnaire_version=version,ratings={},answers={'suggestions':'PRIVATE'}) for version in (1,2) for _ in range(3)]
        with patch('dic.feedback_services.AnonymousCamperResponse.objects') as anonymous,patch('dic.feedback_services.IdentifiedFeedback.objects') as identified:
            anonymous.filter.return_value=rows;identified.filter.return_value=[]
            result=feedback_summary(NS(pk=1),details=True)
        self.assertTrue(all(row['suppressed'] for row in result));self.assertNotIn('PRIVATE',str(result))

    def test_small_applicable_accommodation_group_is_not_exposed(self):
        rows=[NS(channel='daily',day=self.today,questionnaire_version=2,
            ratings={'learning':5, **({'comfort':1} if index==0 else {})},answers={}) for index in range(5)]
        with patch('dic.feedback_services.AnonymousCamperResponse.objects') as anonymous,patch('dic.feedback_services.IdentifiedFeedback.objects') as identified:
            anonymous.filter.return_value=rows;identified.filter.return_value=[]
            result=feedback_summary(NS(pk=1))[0]
        self.assertNotIn('comfort',result['distributions'])
        self.assertEqual(result['distributions']['learning']['5'],5)

    def test_foreign_camper_rejected_by_current_booking_scope(self):
        with patch('dic.feedback_services.authorized_grant'),patch('dic.feedback_services.scoped_orders',return_value=[]),patch('dic.feedback_services.RegistrationOrderItem.objects') as items:
            items.select_related.return_value.filter.return_value.first.return_value=None
            with self.assertRaises(PermissionDenied):portal_item(None,99)
            self.assertEqual(items.select_related.return_value.filter.call_args.kwargs['order_id__in'],[])

    def test_complaint_history_excludes_private_notes_and_other_children(self):
        report=NS(pk=uuid4(),category='health',description='Synthetic concern',urgency='urgent',status='review',created_at=datetime.now(datetime_timezone.utc),note='PRIVATE')
        item=NS(order=NS(edition=self.edition,primary_registrant=NS(pk=4)),participant=NS(pk=7))
        with patch('dic.feedback_api.authorized_grant'),patch('dic.feedback_api.require_feedback_storage'),patch('dic.feedback_api.portal_item',return_value=item),patch('dic.feedback_api.WelfareReport.objects') as reports:
            reports.filter.return_value.order_by.return_value=[report]
            response=CamperWelfareSubmitView.as_view()(APIRequestFactory().get('/?item_id=1'))
        self.assertEqual(response.status_code,200)
        self.assertNotIn('PRIVATE',str(response.data))
        self.assertEqual(reports.filter.call_args.kwargs['affected_participant'],item.participant)
        self.assertEqual(reports.filter.call_args.kwargs['reporter_registrant'],item.order.primary_registrant)

    def test_complaint_post_requires_csrf_before_storage(self):
        with patch('dic.feedback_api.require_feedback_storage') as storage:
            response=CamperWelfareSubmitView.as_view()(APIRequestFactory(enforce_csrf_checks=True).post('/',{'item_id':1},format='json'))
        self.assertEqual(response.status_code,403);storage.assert_not_called()
