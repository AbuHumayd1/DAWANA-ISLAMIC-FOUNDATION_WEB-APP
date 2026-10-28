"""Privacy boundaries without DB access, plus isolated-DB integration fixtures."""
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase,TestCase,override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied,ValidationError,APIException
from rest_framework.test import APIRequestFactory,force_authenticate
from .models import (CampEdition,AnonymousCamperResponse,CamperFeedbackReceipt,IdentifiedFeedback,
    WelfareReport,WelfareEvent,Lecturer,LecturerAppearance,LecturerFeedbackAccess,DICAdminAuditEvent)
from .feedback_schema import QUESTIONS
from .feedback_services import (receipt_digest,validate_response,submit_camper,submit_identified,
    feedback_summary,create_welfare,update_welfare)
from .feedback_api import FeedbackSummaryView,WelfareReportsView,WelfareReportDetailView,IdentifiedFeedbackSubmitView,CamperFeedbackSubmitView


def payload(channel='daily',day=None):
    result=dict(channel=channel,day=str(day or timezone.localdate()),ratings={key:2 for key in QUESTIONS[channel]['ratings']},answers={})
    if channel=='final':result['recommend']=True
    return result


class FeedbackPrivacyTests(SimpleTestCase):
    def actor(self,*permissions,staff=True,active=True):
        allowed={'dic.can_view_dic_operations',*('dic.'+value for value in permissions)}
        return NS(pk=7,is_authenticated=True,is_superuser=False,is_staff=staff,is_active=active,has_perm=lambda name:name in allowed)

    def request(self,view,user,method='get',query='',body=None,**kwargs):
        request=getattr(APIRequestFactory(),method)('/api/v1/dic/operations/feedback/'+query,body or {},format='json')
        if user:force_authenticate(request,user=user)
        return view.as_view()(request,**kwargs)

    def test_anonymous_models_have_no_identity_timestamp_or_response_link(self):
        self.assertEqual({field.name for field in AnonymousCamperResponse._meta.fields},{'id','edition','day','channel','ratings','answers','questionnaire_version'})
        self.assertEqual({field.name for field in CamperFeedbackReceipt._meta.fields},{'digest'})
        self.assertEqual(AnonymousCamperResponse._meta.default_permissions,())

    @override_settings(DIC_FEEDBACK_PRIVACY_KEY='synthetic-test-privacy-key-32-characters-long')
    def test_duplicate_digest_is_private_and_separates_person_day_channel_and_edition(self):
        digest=receipt_digest('participant',1,'2026-12-23','daily')
        self.assertEqual(digest,receipt_digest('participant',1,'2026-12-23','daily'))
        for args in [('other',1,'2026-12-23','daily'),('participant',2,'2026-12-23','daily'),('participant',1,'2026-12-24','daily'),('participant',1,'2026-12-23','final')]:
            self.assertNotEqual(digest,receipt_digest(*args))
        self.assertEqual(len(digest),64);self.assertNotIn('participant',digest)

    @override_settings(DIC_FEEDBACK_PRIVACY_KEY='')
    def test_privacy_key_is_required_without_fallback_to_guessable_identifiers(self):
        with self.assertRaises(APIException):receipt_digest('participant',1,'2026-12-23','daily')

    def test_question_validation_rejects_identity_fields_in_answers_and_wrong_ratings(self):
        edition=NS(camp_start_date=timezone.localdate()-timedelta(days=8),camp_end_date=timezone.localdate())
        self.assertEqual(validate_response(payload(),edition,('daily',))['channel'],'daily')
        for changes in [dict(answers={'email':'private'}),dict(ratings={'identity':2}),dict(ratings={key:6 for key in QUESTIONS['daily']['ratings']}),dict(day=str(timezone.localdate()+timedelta(days=1)))]:
            with self.assertRaises(ValidationError):validate_response({**payload(),**changes},edition,('daily',))

    def test_final_requires_final_day_and_recommendation(self):
        today=timezone.localdate();edition=NS(camp_start_date=today-timedelta(days=8),camp_end_date=today)
        self.assertTrue(validate_response(payload('final'),edition,('final',))['answers']['recommend'])
        with self.assertRaises(ValidationError):validate_response(payload('final',today-timedelta(days=1)),edition,('final',))
        with self.assertRaises(PermissionDenied):validate_response(payload('staff'),edition,('daily','final'))

    def test_feedback_permissions_do_not_grant_welfare_access(self):
        # No database access is allowed by this class, including transaction
        # entry. The real endpoint and require_feedback_staff check run.
        for permissions in [('can_view_dic_feedback',),('can_read_dic_feedback_details',),
                ('can_view_dic_feedback','can_read_dic_feedback_details')]:
            for view,kwargs in [(WelfareReportsView,{}),(WelfareReportDetailView,{'report_id':uuid4()})]:
                with self.subTest(permissions=permissions,view=view.__name__), \
                     patch('dic.feedback_api.require_feedback_storage') as storage, \
                     patch('dic.feedback_api.WelfareReport.objects') as reports, \
                     patch('dic.feedback_api.WelfareEvent.objects') as events:
                    self.assertEqual(self.request(view,self.actor(*permissions),**kwargs).status_code,403)
                    storage.assert_not_called();reports.filter.assert_not_called();events.create.assert_not_called()

    def test_feedback_permissions_cannot_update_confidential_welfare_records(self):
        for permissions in [('can_view_dic_feedback',),('can_read_dic_feedback_details',),
                ('can_view_dic_feedback','can_read_dic_feedback_details')]:
            with self.subTest(permissions=permissions), \
                 patch('dic.feedback_api.require_feedback_storage') as storage, \
                 patch('dic.feedback_api.update_welfare') as update:
                response=self.request(WelfareReportDetailView,self.actor(*permissions),'post','?edition=1',
                    {'status':'closed','note':'Must not be saved','version':1,'assigned_to':None,'request_id':str(uuid4())},report_id=uuid4())
                self.assertEqual(response.status_code,403)
                storage.assert_not_called();update.assert_not_called()

    def test_welfare_view_permission_does_not_grant_management(self):
        with patch('dic.feedback_api.require_feedback_storage') as storage, \
             patch('dic.feedback_api.update_welfare') as update:
            response=self.request(WelfareReportDetailView,self.actor('can_view_dic_welfare'),'post','?edition=1',
                {'status':'closed','note':'Must not be saved','version':1,'assigned_to':None,'request_id':str(uuid4())},report_id=uuid4())
        self.assertEqual(response.status_code,403)
        storage.assert_not_called();update.assert_not_called()

    def test_welfare_management_without_view_permission_is_also_denied(self):
        with patch('dic.feedback_api.require_feedback_storage') as storage, \
             patch('dic.feedback_api.update_welfare') as update:
            response=self.request(WelfareReportDetailView,self.actor('can_manage_dic_welfare'),'post','?edition=1',
                {'status':'review'},report_id=uuid4())
        self.assertEqual(response.status_code,403)
        storage.assert_not_called();update.assert_not_called()

    def test_inactive_nonstaff_and_anonymous_requests_are_rejected(self):
        for user in [None,self.actor('can_view_dic_feedback',active=False),self.actor('can_view_dic_feedback',staff=False)]:
            with patch('dic.feedback_api.require_feedback_storage') as storage:
                self.assertEqual(self.request(FeedbackSummaryView,user).status_code,403)
                storage.assert_not_called()

    def test_staff_lecturer_submission_permissions_checked_before_storage(self):
        for channel in ('staff','lecturer'):
            with patch('dic.feedback_api.require_feedback_storage') as storage:
                self.assertEqual(self.request(IdentifiedFeedbackSubmitView,self.actor(),'post','?edition=1',payload(channel)).status_code,403)
                storage.assert_not_called()

    def test_session_and_camper_post_require_csrf(self):
        for view in (IdentifiedFeedbackSubmitView,CamperFeedbackSubmitView):
            request=APIRequestFactory(enforce_csrf_checks=True).post('/api/v1/dic/participant/feedback/',{},format='json')
            request.user=self.actor('can_submit_dic_staff_feedback')
            with patch('dic.feedback_api.require_feedback_storage') as storage:
                response=view.as_view()(request)
            self.assertEqual(response.status_code,403);storage.assert_not_called()

    def test_export_requires_existing_export_permission(self):
        with patch('dic.feedback_api.require_feedback_storage') as storage:
            self.assertEqual(self.request(FeedbackSummaryView,self.actor('can_view_dic_feedback'),query='?export=csv').status_code,403)
            storage.assert_not_called()

    def test_empty_and_small_aggregate_groups_never_read_welfare_or_receipts(self):
        row=NS(channel='daily',day=timezone.localdate(),ratings={key:2 for key in QUESTIONS['daily']['ratings']},answers={'suggestions':'Private comment'})
        with patch('dic.feedback_services.AnonymousCamperResponse.objects') as anonymous,patch('dic.feedback_services.IdentifiedFeedback.objects') as identified,patch('dic.feedback_services.WelfareReport.objects') as welfare,patch('dic.feedback_services.CamperFeedbackReceipt.objects') as receipts:
            anonymous.filter.return_value=[];identified.filter.return_value=[]
            self.assertEqual(feedback_summary(NS(pk=1)),[])
            anonymous.filter.return_value=[row]
            result=feedback_summary(NS(pk=1),details=True)[0]
            self.assertIsNone(result['count']);self.assertTrue(result['suppressed']);self.assertNotIn('responses',result)
            self.assertNotIn('Private comment',str(result));welfare.filter.assert_not_called();receipts.filter.assert_not_called()

    def test_aggregate_queries_are_edition_scoped_and_5_response_threshold_applies(self):
        edition=NS(pk=1);row=NS(channel='daily',day=timezone.localdate(),ratings={key:3 for key in QUESTIONS['daily']['ratings']},answers={})
        with patch('dic.feedback_services.AnonymousCamperResponse.objects') as anonymous,patch('dic.feedback_services.IdentifiedFeedback.objects') as identified:
            anonymous.filter.return_value=[row]*5;identified.filter.return_value=[]
            result=feedback_summary(edition)[0]
            anonymous.filter.assert_called_once_with(edition=edition);identified.filter.assert_called_once_with(edition=edition)
        self.assertEqual(result['count'],5);self.assertFalse(result['suppressed']);self.assertNotIn('responses',result)

    def test_welfare_channel_cannot_be_selected_for_general_export(self):
        with patch('dic.feedback_api.require_feedback_storage'),patch('dic.feedback_api._edition_from_request',return_value=NS(pk=1)),patch('dic.feedback_api.feedback_summary') as summary:
            response=self.request(FeedbackSummaryView,self.actor('can_view_dic_feedback','can_export_dic_reports'),query='?channel=welfare&export=csv')
        self.assertEqual(response.status_code,400);summary.assert_not_called()


@override_settings(DIC_FEEDBACK_PRIVACY_KEY='synthetic-test-privacy-key-32-characters-long')
class FeedbackIntegrationTests(TestCase):
    """Only run in an explicitly approved isolated migrated test database."""
    def setUp(self):
        today=timezone.localdate()
        self.edition=CampEdition.objects.create(name='SYNTHETIC Feedback Camp',year=2099,camp_start_date=today-timedelta(days=8),camp_end_date=today)
        self.staff=get_user_model().objects.create_user(username='synthetic-welfare-staff',is_staff=True,is_superuser=True)

    def test_daily_final_responses_unlinked_and_retries_do_not_duplicate(self):
        item=NS(participant_id=uuid4(),order=NS(edition=self.edition,edition_id=self.edition.pk,registration_basis='paid'))
        with patch('dic.feedback_services.portal_item',return_value=item):
            self.assertTrue(submit_camper(None,1,payload()))
            self.assertFalse(submit_camper(None,1,payload()))
            self.assertTrue(submit_camper(None,1,payload('final')))
        self.assertEqual(AnonymousCamperResponse.objects.count(),2);self.assertEqual(CamperFeedbackReceipt.objects.count(),2)
        self.assertEqual(DICAdminAuditEvent.objects.count(),0)
        for row in AnonymousCamperResponse.objects.values():
            self.assertNotIn('participant',str(row));self.assertNotIn('author',str(row));self.assertNotIn('created_at',row)

    def test_identified_complaints_keep_affected_children_and_private_notes_separate(self):
        from .models import PrimaryRegistrant, Participant
        from .feedback_api import CamperWelfareSubmitView
        guardian=PrimaryRegistrant.objects.create(full_name='SYNTHETIC guardian',email='guardian@example.test')
        children=[Participant.objects.create(full_name='SYNTHETIC child '+str(index),
            address='SYNTHETIC',phone='',email='',date_of_birth=timezone.localdate()-timedelta(days=3650),
            sex='Female',academic_status='Primary Student',occupation='None',marital_status='None') for index in (1,2)]
        reports=[]
        for child in children:
            report,created=create_welfare(self.edition,dict(category='health',description='SYNTHETIC concern',
                urgency='urgent',preferred_contact='in_person',request_id=str(uuid4())),registrant=guardian,participant=child)
            self.assertTrue(created);reports.append(report)
        WelfareEvent.objects.create(report=reports[0],actor=self.staff,kind='updated',note='CONFIDENTIAL-OFFICER-NOTE')
        item=NS(order=NS(edition=self.edition,primary_registrant=guardian),participant=children[0])
        with patch('dic.feedback_api.authorized_grant'),patch('dic.feedback_api.portal_item',return_value=item):
            response=CamperWelfareSubmitView.as_view()(APIRequestFactory().get('/?item_id=1'))
        self.assertEqual([row['id'] for row in response.data['results']],[str(reports[0].pk)])
        self.assertNotIn('CONFIDENTIAL-OFFICER-NOTE',str(response.data))
        with self.assertRaises(ValidationError):
            create_welfare(self.edition,dict(category='health',description='SYNTHETIC',request_id=str(uuid4())),registrant=guardian)

    def test_complaint_retry_cannot_change_affected_child_or_urgency(self):
        payload=dict(category='health',description='SYNTHETIC concern',request_id=str(uuid4()))
        report,created=create_welfare(self.edition,payload,user=self.staff)
        self.assertTrue(created)
        duplicate,created=create_welfare(self.edition,payload,user=self.staff)
        self.assertFalse(created);self.assertEqual(duplicate.pk,report.pk)
        with self.assertRaises(ValidationError):create_welfare(self.edition,{**payload,'urgency':'urgent'},user=self.staff)

    def test_final_receipt_survives_corrected_camp_end_date(self):
        item=NS(participant_id=uuid4(),order=NS(edition=self.edition,edition_id=self.edition.pk,registration_basis='paid'))
        with patch('dic.feedback_services.portal_item',return_value=item):
            self.assertTrue(submit_camper(None,1,payload('final')))
            self.edition.camp_end_date+=timedelta(days=1)
            self.edition.save(update_fields=['camp_end_date'])
            with patch('dic.feedback_services.camp_today',return_value=self.edition.camp_end_date):
                self.assertFalse(submit_camper(None,1,payload('final',self.edition.camp_end_date)))
        self.assertEqual(AnonymousCamperResponse.objects.count(),1)

    def test_historical_final_receipt_remains_effective(self):
        participant_id=uuid4();old_day=self.edition.camp_end_date-timedelta(days=1)
        AnonymousCamperResponse.objects.create(edition=self.edition,day=old_day,channel='final',
            questionnaire_version=1,ratings={'overall':3,'knowledge':3},answers={'recommend':True})
        CamperFeedbackReceipt.objects.create(digest=receipt_digest(participant_id,self.edition.pk,old_day,'final'))
        item=NS(participant_id=participant_id,order=NS(edition=self.edition,edition_id=self.edition.pk,registration_basis='paid'))
        with patch('dic.feedback_services.portal_item',return_value=item):
            self.assertFalse(submit_camper(None,1,payload('final')))
        self.assertEqual(AnonymousCamperResponse.objects.count(),1)

    def test_staff_identified_and_lecturer_requires_real_mapping(self):
        self.assertTrue(submit_identified(self.edition,self.staff,payload('staff')))
        self.assertFalse(submit_identified(self.edition,self.staff,payload('staff')))
        self.assertEqual(IdentifiedFeedback.objects.get().author_id,self.staff.pk)
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,self.staff,payload('lecturer'))
        lecturer=Lecturer.objects.create(name='SYNTHETIC Lecturer',alt_text='SYNTHETIC',biography='SYNTHETIC')
        appearance=LecturerAppearance.objects.create(lecturer=lecturer,edition=self.edition,participation_type='previous',
            verification_note='SYNTHETIC recorded evidence for authorised lecturer verification')
        self.verify_appearance(appearance)
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,self.staff,payload('lecturer'))
        LecturerFeedbackAccess.objects.create(lecturer=lecturer,edition=self.edition,user=self.staff)
        self.assertTrue(submit_identified(self.edition,self.staff,payload('lecturer')))
        response=IdentifiedFeedback.objects.get(channel='lecturer')
        self.assertEqual((response.author_id,response.lecturer_id),(self.staff.pk,lecturer.pk))

    def verify_appearance(self,appearance):
        from django.contrib import admin
        from django.test import RequestFactory
        from .showcase_admin import LecturerAppearanceAdmin
        request=RequestFactory().post('/admin/dic/lecturerappearance/')
        request.user=self.staff
        LecturerAppearanceAdmin(LecturerAppearance,admin.AdminSite()).verify_selected(
            request,LecturerAppearance.objects.filter(pk=appearance.pk))
        appearance.refresh_from_db()
        self.assertTrue(appearance.verified)
        self.assertEqual(appearance.verified_by_id,self.staff.pk)
        self.assertIsNotNone(appearance.verified_at)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='lecturer_participation_verified',actor=self.staff,target_id=str(appearance.pk)).exists())

    def test_lecturer_mapping_requires_verified_appearance_in_the_same_edition(self):
        lecturer=Lecturer.objects.create(name='SYNTHETIC mapped lecturer',alt_text='SYNTHETIC',biography='SYNTHETIC')
        LecturerFeedbackAccess.objects.create(lecturer=lecturer,edition=self.edition,user=self.staff)
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,self.staff,payload('lecturer'))
        appearance=LecturerAppearance.objects.create(lecturer=lecturer,edition=self.edition,participation_type='previous',verification_note='SYNTHETIC evidence')
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,self.staff,payload('lecturer'))
        self.verify_appearance(appearance)
        other=CampEdition.objects.create(name='SYNTHETIC wrong edition',year=2101,camp_start_date=self.edition.camp_start_date,camp_end_date=self.edition.camp_end_date)
        # A verified appearance and mapping in the original edition do not
        # authorise submission for another edition, even with a foreign mapping.
        with self.assertRaises(PermissionDenied):submit_identified(other,self.staff,payload('lecturer'))
        LecturerFeedbackAccess.objects.create(lecturer=lecturer,edition=other,user=self.staff)
        with self.assertRaises(PermissionDenied):submit_identified(other,self.staff,payload('lecturer'))
        self.assertFalse(IdentifiedFeedback.objects.filter(edition=other).exists())
        self.assertTrue(submit_identified(self.edition,self.staff,payload('lecturer')))

    def test_lecturer_feedback_rejects_incomplete_verification_metadata(self):
        lecturer=Lecturer.objects.create(name='SYNTHETIC verification integrity',alt_text='SYNTHETIC',biography='SYNTHETIC')
        appearance=LecturerAppearance.objects.create(lecturer=lecturer,edition=self.edition,participation_type='previous',verification_note='SYNTHETIC evidence')
        self.verify_appearance(appearance)
        LecturerFeedbackAccess.objects.create(lecturer=lecturer,edition=self.edition,user=self.staff)
        # Deliberately simulate legacy/corrupt metadata only in the isolated DB.
        LecturerAppearance.objects.filter(pk=appearance.pk).update(verified_at=None)
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,self.staff,payload('lecturer'))
        self.assertFalse(IdentifiedFeedback.objects.exists())

    def test_staff_and_lecturer_submission_permissions_are_separate(self):
        from django.contrib.auth.models import Permission
        def account(name,permission):
            user=get_user_model().objects.create_user(username=name,is_staff=True)
            grants=Permission.objects.filter(content_type__app_label='dic',codename__in=['can_view_dic_operations',permission])
            self.assertEqual(grants.count(),2)
            user.user_permissions.add(*grants)
            return user
        staff=account('synthetic-staff-feedback-only','can_submit_dic_staff_feedback')
        lecturer_user=account('synthetic-lecturer-feedback-only','can_submit_dic_lecturer_feedback')
        lecturer=Lecturer.objects.create(name='SYNTHETIC permission lecturer',alt_text='SYNTHETIC',biography='SYNTHETIC')
        appearance=LecturerAppearance.objects.create(lecturer=lecturer,edition=self.edition,participation_type='previous',verification_note='SYNTHETIC evidence')
        self.verify_appearance(appearance)
        LecturerFeedbackAccess.objects.create(lecturer=lecturer,edition=self.edition,user=lecturer_user)
        self.assertTrue(submit_identified(self.edition,staff,payload('staff')))
        self.assertEqual(IdentifiedFeedback.objects.get(channel='staff').author_id,staff.pk)
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,staff,payload('lecturer'))
        with self.assertRaises(PermissionDenied):submit_identified(self.edition,lecturer_user,payload('staff'))
        self.assertTrue(submit_identified(self.edition,lecturer_user,payload('lecturer')))
        self.assertEqual(IdentifiedFeedback.objects.get(channel='lecturer').author_id,lecturer_user.pk)

    def test_welfare_lifecycle_audits_stay_private_and_updates_are_idempotent(self):
        data=dict(category='health',description='SYNTHETIC confidential concern',assistance_person='SYNTHETIC person',request_id=str(uuid4()))
        report,created=create_welfare(self.edition,data,user=self.staff);self.assertTrue(created)
        duplicate,created=create_welfare(self.edition,data,user=self.staff);self.assertFalse(created);self.assertEqual(duplicate.pk,report.pk)
        update=dict(status='review',assigned_to=self.staff.pk,note='SYNTHETIC private follow-up',version=1,request_id=str(uuid4()))
        report,changed=update_welfare(self.edition,report.pk,self.staff,update);self.assertTrue(changed)
        _,changed=update_welfare(self.edition,report.pk,self.staff,update);self.assertFalse(changed)
        self.assertEqual(WelfareEvent.objects.filter(report=report,kind='updated').count(),1)
        self.assertEqual(DICAdminAuditEvent.objects.count(),0)
        self.assertEqual(feedback_summary(self.edition),[])
        with self.assertRaises(ValidationError):update_welfare(self.edition,report.pk,self.staff,{**update,'request_id':str(uuid4())})
        for status in ('resolved','closed'):
            report,_=update_welfare(self.edition,report.pk,self.staff,{**update,'status':status,'version':report.version,'request_id':str(uuid4())})
        self.assertEqual(report.status,'closed')

    def test_welfare_other_edition_and_unauthorised_reads_rejected_authorised_access_logged(self):
        data=dict(category='other',description='SYNTHETIC confidential',request_id=str(uuid4()))
        report,_=create_welfare(self.edition,data,user=self.staff)
        other=CampEdition.objects.create(name='SYNTHETIC Other',year=2100,camp_start_date=self.edition.camp_start_date,camp_end_date=self.edition.camp_end_date)
        with self.assertRaises(ValidationError):update_welfare(other,report.pk,self.staff,dict(status='review',assigned_to=None,note='Test',version=1,request_id=str(uuid4())))
        request=APIRequestFactory().get(f'/api/v1/dic/operations/welfare/{report.pk}/?edition={self.edition.pk}')
        force_authenticate(request,user=self.staff)
        response=WelfareReportDetailView.as_view()(request,report_id=report.pk)
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['description'],'SYNTHETIC confidential')
        self.assertEqual(WelfareEvent.objects.filter(report=report,kind='viewed').count(),1)

    def test_real_permission_grants_separate_feedback_welfare_view_and_management(self):
        from django.contrib.auth.models import Permission
        report,_=create_welfare(self.edition,dict(category='other',description='SYNTHETIC private report',request_id=str(uuid4())),user=self.staff)
        original_status,original_version=report.status,report.version

        def account(name,permissions):
            user=get_user_model().objects.create_user(username=name,is_staff=True)
            grants=Permission.objects.filter(content_type__app_label='dic',codename__in=['can_view_dic_operations',*permissions])
            self.assertEqual(grants.count(),1+len(permissions))
            user.user_permissions.add(*grants)
            return user

        def send(view,user,method='get',detail=False):
            request=getattr(APIRequestFactory(),method)(f'/api/v1/dic/operations/welfare/?edition={self.edition.pk}',
                {'status':'closed','note':'Must not be saved','version':original_version,'assigned_to':None,'request_id':str(uuid4())} if method=='post' else {},format='json')
            force_authenticate(request,user=user)
            return view.as_view()(request,**({'report_id':report.pk} if detail else {}))

        for index,permissions in enumerate([['can_view_dic_feedback'],['can_read_dic_feedback_details'],
                ['can_view_dic_feedback','can_read_dic_feedback_details']]):
            user=account(f'synthetic-general-feedback-{index}',permissions)
            with self.subTest(permissions=permissions):
                self.assertEqual(send(WelfareReportsView,user).status_code,403)
                self.assertEqual(send(WelfareReportDetailView,user,detail=True).status_code,403)
                self.assertEqual(send(WelfareReportDetailView,user,'post',detail=True).status_code,403)
        self.assertEqual(WelfareEvent.objects.filter(report=report,kind='viewed').count(),0)

        viewer=account('synthetic-welfare-viewer',['can_view_dic_welfare'])
        response=send(WelfareReportDetailView,viewer,detail=True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['description'],'SYNTHETIC private report')
        self.assertEqual(WelfareEvent.objects.filter(report=report,kind='viewed',actor=viewer).count(),1)
        self.assertEqual(send(WelfareReportDetailView,viewer,'post',detail=True).status_code,403)
        report.refresh_from_db()
        self.assertEqual((report.status,report.version),(original_status,original_version))
        self.assertEqual(WelfareEvent.objects.filter(report=report,kind='updated').count(),0)
