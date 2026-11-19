"""Database acceptance for approved committee reports and editor authorization."""
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dic.models import CampEdition, AftercampAssessment, DICAdminAuditEvent
from dic.aftercamp_evidence import approved_assessments


class AftercampCommitteeWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.edition=CampEdition.objects.create(name='Synthetic camp 2041',year=2041,
            camp_start_date=date(2041,12,23),camp_end_date=date(2042,1,1))
        cls.admin=get_user_model().objects.create_superuser(
            username='aftercamp-review-admin',email='review@example.test',password='safe-test-password')
        cls.operator=get_user_model().objects.create_user(
            username='aftercamp-review-operator',email='other@example.test',password='safe-test-password',
            is_staff=True)

    def endpoint(self, **changes):
        return {'edition':self.edition.pk, 'topic':'programme', **changes}

    def test_approval_requires_saved_evidence_and_drafts_are_excluded(self):
        self.client.force_login(self.admin)
        url=reverse('dic:operations-aftercamp-report')
        response=self.client.post(url,data=self.endpoint(
            action='save',findings='Seven programme sessions recorded',
            evidence_reference='Approved committee minutes A-1'),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(approved_assessments(self.edition),[])
        assessment=AftercampAssessment.objects.get(edition=self.edition,topic='programme')
        self.assertEqual(assessment.status,'draft')
        response=self.client.post(url,data=self.endpoint(action='approve'),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(approved_assessments(self.edition)[0]['findings'],
                         'Seven programme sessions recorded')
        self.assertEqual(approved_assessments(self.edition)[0]['evidence_reference'],
                         'Approved committee minutes A-1')
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='aftercamp_assessment_approve').exists())
        # Approval is immutable until explicitly reopened; drafts remain private.
        response=self.client.post(url,data=self.endpoint(action='save',
            findings='Unreviewed revised draft'),content_type='application/json')
        self.assertEqual(response.status_code,400)
        response=self.client.post(url,data=self.endpoint(action='reopen'),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(approved_assessments(self.edition),[])

    def test_missing_evidence_cannot_be_approved(self):
        self.client.force_login(self.admin)
        url=reverse('dic:operations-aftercamp-report')
        response=self.client.post(url,data=self.endpoint(action='approve'),content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertFalse(AftercampAssessment.objects.filter(
            edition=self.edition,topic='programme',status='approved').exists())

    def test_non_admin_editor_is_denied_before_any_write(self):
        self.client.force_login(self.operator)
        url=reverse('dic:operations-aftercamp-report')
        response=self.client.post(url,data=self.endpoint(action='save',
            findings='Not authorized',evidence_reference='Private'),content_type='application/json')
        self.assertEqual(response.status_code,403)
        self.assertFalse(AftercampAssessment.objects.exists())
