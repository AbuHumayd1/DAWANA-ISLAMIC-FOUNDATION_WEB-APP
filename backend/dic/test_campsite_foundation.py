"""Database-free boundary tests. No fixture users, model writes or DB setup."""
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.exceptions import ValidationError
from .campsite_api import CampsiteOverviewView


class CampsiteFoundationTests(SimpleTestCase):
    def user(self, *, staff=True, active=True, operations=True):
        return SimpleNamespace(is_authenticated=True,is_active=active,is_staff=staff,is_superuser=False,
            has_perm=lambda permission: operations and permission=='dic.can_view_dic_operations')

    def request(self, user, query=''):
        request = APIRequestFactory().get('/api/v1/dic/operations/campsite/'+query)
        if user is not None:
            force_authenticate(request,user=user)
        return CampsiteOverviewView.as_view()(request)

    def test_denied_users_never_query_operational_data(self):
        for user in (None,AnonymousUser(),self.user(staff=False),self.user(active=False),self.user(operations=False)):
            with self.subTest(user=user), patch('dic.campsite_api._edition_from_request') as select:
                self.assertEqual(self.request(user).status_code,403)
                select.assert_not_called()

    def test_selected_edition_is_passed_to_summary_and_sensitive_values_are_absent(self):
        edition = SimpleNamespace(pk=2026,name='Synthetic Edition',year=2026)
        summary = dict(registered_participants=0,attendance=None)
        with patch('dic.campsite_api._edition_from_request',return_value=edition) as select, \
             patch('dic.campsite_api.CampEdition.objects') as editions, \
             patch('dic.campsite_api.campsite_metrics',return_value=summary) as metrics:
            editions.order_by.return_value.values.return_value = []
            response = self.request(self.user(),'?edition=2026')
        self.assertEqual(response.status_code,200)
        self.assertEqual(select.call_args.args[0].query_params['edition'],'2026')
        metrics.assert_called_once_with(edition)
        self.assertEqual(response.data['edition']['id'],2026)
        self.assertEqual(response['Cache-Control'],'no-store')
        for private in ('verification_secret','verification_digest','phone','email','address'):
            self.assertNotIn(private,str(response.data))

    def test_no_edition_returns_unavailable_metrics_without_global_fallback(self):
        with patch('dic.campsite_api._edition_from_request',return_value=None), \
             patch('dic.campsite_api.CampEdition.objects') as editions, \
             patch('dic.campsite_api.campsite_metrics') as metrics:
            editions.order_by.return_value.values.return_value = []
            response = self.request(self.user())
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.data['edition'])
        self.assertIsNone(response.data['metrics'])
        metrics.assert_not_called()

    def test_invalid_edition_is_rejected_and_post_is_not_implemented(self):
        with patch('dic.campsite_api._edition_from_request',side_effect=ValidationError('Invalid edition')), \
             patch('dic.campsite_api.campsite_metrics') as metrics:
            self.assertEqual(self.request(self.user(),'?edition=invalid').status_code,400)
            metrics.assert_not_called()
        request = APIRequestFactory().post('/api/v1/dic/operations/campsite/',{})
        force_authenticate(request,user=self.user())
        self.assertEqual(CampsiteOverviewView.as_view()(request).status_code,405)

    def test_real_edition_selector_requires_existing_edition(self):
        from .operations_api import _edition_from_request
        for value in ('invalid','999999'):
            with patch('dic.operations_api.CampEdition.objects') as editions:
                from .models import CampEdition
                editions.all.return_value.get.side_effect = CampEdition.DoesNotExist
                request = SimpleNamespace(query_params={'edition':value})
                with self.assertRaises(ValidationError):
                    _edition_from_request(request)

    def test_summary_uses_existing_eligibility_distinct_people_and_scoped_queries_only(self):
        from .campsite_api import campsite_metrics
        edition = SimpleNamespace(pk=41)
        rows = [SimpleNamespace(participant_id=index,participant=SimpleNamespace(pk=index),
            order=SimpleNamespace(status='cancelled' if index==5 else 'confirmed', registration_basis='paid'),pk=index) for index in range(1,6)]
        enrollments = [SimpleNamespace(participant_id=index) for index in (1,3,4,5)]
        codes = {1:'verified_paid',2:'verified_paid',3:'registration_not_verified_paid',
                 4:'settlement_evidence_review_required',5:'registration_not_verified_paid'}
        def outcome(enrollment):
            code = codes[enrollment.participant_id]
            return {'eligible':code=='verified_paid','code':code}
        with patch('dic.campsite_api.RegistrationOrderItem.objects') as items, \
             patch('dic.campsite_api.CampEnrollment') as enrollment_model, \
             patch('dic.campsite_api.HouseAllocation.objects') as housing, \
             patch('dic.campsite_api.DigitalIDIssue.objects') as issues, \
             patch('dic.campsite_api.eligibility',side_effect=outcome) as eligibility_check:
            items.filter.return_value.select_related.return_value.order_by.return_value = rows+[rows[0]]
            enrollment_model.objects.filter.return_value.select_related.return_value = enrollments
            enrollment_model.return_value = SimpleNamespace(participant_id=2)
            housing.filter.return_value.values_list.return_value = [1,99]
            issues.filter.return_value.exclude.return_value.values.return_value.distinct.return_value.count.return_value = 1
            result = campsite_metrics(edition)
            items.filter.assert_called_once_with(order__edition=edition)
            enrollment_model.objects.filter.assert_called_once_with(edition=edition)
            housing.filter.assert_called_once_with(edition=edition,status='allocated')
            self.assertEqual(issues.filter.call_args.kwargs['enrollment__edition'],edition)
            self.assertEqual(issues.filter.call_args.kwargs['enrollment__participant_id__in'],{1,2})
            self.assertEqual(eligibility_check.call_count,5)
            enrollment_model.assert_called_once_with(participant=rows[1].participant,edition=edition,source_item=rows[1])
        self.assertEqual(result,dict(registered_participants=5,eligible_participants=2,
            awaiting_payment_verification=1,assigned_participants=1,awaiting_house_assignment=1,
            active_ids=1,requiring_attention=2,complimentary_tutors=0,attendance=None))
