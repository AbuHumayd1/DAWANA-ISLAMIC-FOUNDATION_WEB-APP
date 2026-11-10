"""Database-free contract/authority tests; run only through the policy harness."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from . import fulfillment
from .feedback_schema import questionnaire, participant_questionnaire, rating_scale
from .feedback_services import ResponseInput, validate_response, feedback_summary, receipt_digest


class FeedbackVersionPolicyTests(SimpleTestCase):
    day = date(2026, 12, 24)

    def payload(self, version=3, tutor=False):
        spec = questionnaire('daily', tutor=tutor, version=version)
        return dict(channel='daily', day=str(self.day), questionnaire_version=version,
                    ratings={key: 3 for key in spec['ratings']}, answers={'suggestions': ''})

    def validate(self, payload, **kwargs):
        edition = SimpleNamespace(camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1))
        with patch('dic.feedback_services.camp_today', return_value=self.day):
            return validate_response(payload, edition, ('daily', 'final'), **kwargs)

    def test_six_question_contract_and_scale_are_explicit(self):
        spec = participant_questionnaire('daily')
        self.assertEqual(spec['version'], 3)
        self.assertEqual(len(spec['ratings']), 6)
        self.assertEqual(dict(spec['scale']), {1: 'Poor', 2: 'Fair', 3: 'Good', 4: 'Very Good', 5: 'Excellent'})
        self.assertEqual(self.validate(self.payload())['questionnaire_version'], 3)

    def test_old_scale_and_default_client_contract_remain_v2(self):
        self.assertEqual(dict(rating_scale(2))[3], 'Fair')
        self.assertEqual(dict(rating_scale(1))[3], 'Good')
        payload = self.payload(2)
        payload.pop('questionnaire_version')
        self.assertEqual(self.validate(payload)['questionnaire_version'], 2)
        self.assertEqual(participant_questionnaire('final')['version'], 2)

    def test_tutor_accommodation_is_not_invented(self):
        spec = participant_questionnaire('daily', tutor=True)
        self.assertNotIn('comfort', spec['ratings'])
        self.assertEqual(len(spec['ratings']), 5)
        self.validate(self.payload(tutor=True), tutor=True)
        with self.assertRaises(ValidationError):
            self.validate(self.payload(), tutor=True)

    def test_wrong_version_question_keys_and_identity_are_rejected(self):
        for mutation in ({'questionnaire_version': 1}, {'questionnaire_version': 99},
                         {'participant_name': 'PRIVATE'}, {'questionnaire_version': 2}):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValidationError) as error:
                    self.validate({**self.payload(), **mutation})
                if mutation.get('questionnaire_version') in (1, 99):
                    self.assertIn('questionnaire_version', error.exception.detail)
                elif 'participant_name' in mutation:
                    self.assertEqual(error.exception.detail, {
                        api_settings.NON_FIELD_ERRORS_KEY: ['Only the documented feedback fields are accepted.']})
        with self.assertRaises(ValidationError):
            self.validate({**self.payload(), 'channel': 'final'})

    def test_serializer_rejections_have_mapping_errors_with_and_without_raising(self):
        expected = {api_settings.NON_FIELD_ERRORS_KEY: ['Only the documented feedback fields are accepted.']}
        for payload in ({**self.payload(), 'participant_name': 'PRIVATE'}, [], 'not a feedback object'):
            for raise_exception in (False, True):
                with self.subTest(payload_type=type(payload).__name__, raise_exception=raise_exception):
                    form = ResponseInput(data=payload)
                    if raise_exception:
                        with self.assertRaises(ValidationError) as error:
                            form.is_valid(raise_exception=True)
                        self.assertEqual(error.exception.detail, expected)
                    else:
                        self.assertFalse(form.is_valid())
                    self.assertEqual(form.errors, expected)
                    self.assertEqual(form.validated_data, {})

    def test_unknown_rating_and_answer_keys_keep_existing_service_errors(self):
        for mutation in ({'ratings': {**self.payload()['ratings'], 'identity': 3}},
                         {'answers': {'participant_name': 'PRIVATE'}}):
            with self.subTest(field=next(iter(mutation))):
                with self.assertRaises(ValidationError) as error:
                    self.validate({**self.payload(), **mutation})
                self.assertEqual(error.exception.detail, [
                    'Answer the displayed rating questions only; do not send identity fields.'])

    def test_duplicate_receipt_is_not_version_dependent(self):
        with self.settings(DIC_FEEDBACK_PRIVACY_KEY='synthetic-only-privacy-key-longer-than-32'):
            self.assertEqual(receipt_digest('synthetic', 1, self.day, 'daily'),
                             receipt_digest('synthetic', 1, self.day, 'daily'))
        # There is deliberately no version parameter: a new form cannot bypass a receipt.
        import inspect
        self.assertNotIn('version', inspect.signature(receipt_digest).parameters)

    def test_reports_keep_versions_labels_and_privacy_threshold_separate(self):
        rows = [SimpleNamespace(channel='daily', day=self.day, questionnaire_version=version,
                    ratings={'learning': 3}, answers={}) for version in (2, 3) for _ in range(5)]
        with patch('dic.feedback_services.AnonymousCamperResponse.objects.filter', return_value=rows), \
             patch('dic.feedback_services.IdentifiedFeedback.objects.filter', return_value=[]):
            groups = feedback_summary(SimpleNamespace())
        self.assertEqual([group['questionnaire_version'] for group in groups], [2, 3])
        self.assertEqual([dict(group['scale'])[3] for group in groups], ['Fair', 'Good'])
        with patch('dic.feedback_services.AnonymousCamperResponse.objects.filter', return_value=rows[:4]), \
             patch('dic.feedback_services.IdentifiedFeedback.objects.filter', return_value=[]):
            small = feedback_summary(SimpleNamespace(), details=True)[0]
        self.assertTrue(small['suppressed'])
        self.assertEqual(small['distributions'], {})
        self.assertNotIn('responses', small)


class FulfillmentPolicyTests(SimpleTestCase):
    def test_successful_sibling_is_not_reissued_when_another_needs_review(self):
        order = SimpleNamespace(registration_basis='paid', status='confirmed', payment_status='paid')
        job = SimpleNamespace(order_id=1)
        items = [SimpleNamespace(pk=1), SimpleNamespace(pk=2)]
        with patch.object(fulfillment.RegistrationOrder.objects, 'get', return_value=order), \
             patch('dic.settlement_evidence.order_has_verified_settlement', return_value=True), \
             patch.object(fulfillment.transaction, 'atomic'), \
             patch.object(fulfillment, '_issue_item', side_effect=[None, fulfillment.FulfillmentHold('existing_id_requires_review')]) as issue, \
             patch.object(fulfillment, 'audit') as audit:
            state, reason = fulfillment._complete(job, 'synthetic-actor', items, set())
        self.assertEqual((state, reason), ('held', 'existing_id_requires_review'))
        self.assertEqual(issue.call_count, 2)
        self.assertEqual([call.args[1] for call in audit.call_args_list], ['item_completed', 'item_held'])

    def test_revoked_credential_requires_review_instead_of_replacement(self):
        with patch.object(fulfillment, 'ensure_enrollment', return_value=SimpleNamespace(pk=1)), \
             patch.object(fulfillment, 'eligibility', return_value={'eligible': True}), \
             patch.object(fulfillment.DigitalIDIssue.objects, 'filter', return_value=[SimpleNamespace(revoked_at=True)]), \
             patch.object(fulfillment, 'id_command') as issue:
            with self.assertRaises(fulfillment.FulfillmentHold):
                fulfillment._issue_item(SimpleNamespace(pk=1), 'synthetic-actor')
        issue.assert_not_called()

    @override_settings(DIC_AUTO_FULFILLMENT_ENABLED=False)
    def test_disabled_paths_never_access_storage_or_authority(self):
        with patch.object(fulfillment.CamperFulfillmentJob, 'objects') as jobs:
            self.assertIsNone(fulfillment.enqueue_verified(None, None))
            self.assertIsNone(fulfillment.portal_status(None))
            self.assertEqual(fulfillment.process(1), 'disabled')
            self.assertIsNone(fulfillment.dispatch(1))
            self.assertEqual(jobs.mock_calls, [])

    @override_settings(DIC_AUTO_FULFILLMENT_ENABLED=True)
    def test_unverified_payment_cannot_enqueue(self):
        order = SimpleNamespace(registration_basis='paid', status='submitted', payment_status='pending')
        with patch.object(fulfillment.CamperFulfillmentJob, 'objects') as jobs:
            self.assertIsNone(fulfillment.enqueue_verified(order, None))
            self.assertEqual(jobs.mock_calls, [])

    @override_settings(DIC_AUTO_FULFILLMENT_ENABLED=True)
    def test_conflicting_settlement_cannot_enqueue(self):
        order = SimpleNamespace(pk=1, registration_basis='paid', status='confirmed', payment_status='paid')
        attempt = SimpleNamespace(order_id=1, status='successful', provider_status='success',
            verified_at=True, provider_paid_at=True, provider_transaction_id='synthetic')
        with patch('dic.settlement_evidence.settlement_reason', return_value=''), \
             patch('dic.settlement_evidence.order_has_verified_settlement', return_value=False), \
             patch.object(fulfillment.CamperFulfillmentJob, 'objects') as jobs:
            self.assertIsNone(fulfillment.enqueue_verified(order, attempt))
            self.assertEqual(jobs.mock_calls, [])

    @override_settings(DIC_AUTO_FULFILLMENT_ACTOR_ID=0)
    def test_unconfigured_authority_never_looks_up_user(self):
        with patch.object(fulfillment, 'get_user_model') as users:
            with self.assertRaises(fulfillment.FulfillmentHold):
                fulfillment.authority()
            users.assert_not_called()

    @override_settings(DIC_AUTO_FULFILLMENT_ENABLED=True)
    def test_replay_keeps_existing_job_and_does_not_dispatch(self):
        order = SimpleNamespace(pk=1, registration_basis='paid', status='confirmed', payment_status='paid')
        attempt = SimpleNamespace(order_id=1, status='successful', provider_status='success',
            verified_at=True, provider_paid_at=True, provider_transaction_id='synthetic')
        job = SimpleNamespace(pk=9, state='held')
        with patch('dic.settlement_evidence.settlement_reason', return_value=''), \
             patch('dic.settlement_evidence.order_has_verified_settlement', return_value=True), \
             patch.object(fulfillment.CamperFulfillmentJob.objects, 'get_or_create', return_value=(job, False)), \
             patch.object(fulfillment, 'audit') as audit, patch.object(fulfillment, 'dispatch') as dispatch:
            self.assertEqual(fulfillment.enqueue_verified(order, attempt), 9)
            self.assertEqual(job.state, 'held')
            audit.assert_not_called()
            dispatch.assert_not_called()


class RecoveryAuthorizationTests(SimpleTestCase):
    def test_authorized_card_summary_includes_the_enrollment_id_for_download_links(self):
        from uuid import uuid4
        from .participant_api import card_data
        enrollment = SimpleNamespace(pk=uuid4(), participant=SimpleNamespace(), edition=SimpleNamespace(
            name='Synthetic camp', camp_start_date=date(2026, 12, 23),
            camp_end_date=date(2027, 1, 1), venue_name='Synthetic venue'))
        summary = dict(name='Synthetic camper', participant_number='SYNTHETIC-ID', category='Synthetic category',
            eligibility={'eligible': True}, issue={'status': 'current', 'version': 1})
        with self.settings(DIC_OFFICIAL_LOGO_URL=''), patch('dic.participant_api.id_summary', return_value=summary), \
                patch('dic.participant_api.HouseAllocation.objects') as allocations:
            allocations.filter.return_value.select_related.return_value.count.return_value = 0
            result = card_data(enrollment)
        self.assertEqual(result['id'], str(enrollment.pk))
        self.assertEqual(result['participant_number'], 'SYNTHETIC-ID')

    def test_admin_login_inherits_public_return_link(self):
        from django.template.loader import render_to_string
        from config.site_context import public_site
        with self.settings(FRONTEND_ORIGIN='https://frontend.example.test', DEBUG=False):
            html = render_to_string('admin/login.html', public_site(None))
        self.assertIn('href="https://frontend.example.test/" class="admin-public-return"', html)
        self.assertIn('Return to Main Website', html)

    def test_public_return_link_uses_validated_frontend_origin_only(self):
        from config.site_context import public_site
        with self.settings(FRONTEND_ORIGIN='https://frontend.example.test', DEBUG=False):
            self.assertEqual(public_site(None)['public_site_url'], 'https://frontend.example.test/')
        for value in ('//evil.test', 'http://evil.test', 'https://user:pass@evil.test',
                      'https://frontend.example.test/?token=private', 'javascript:alert(1)'):
            with self.settings(FRONTEND_ORIGIN=value, DEBUG=False):
                self.assertEqual(public_site(None)['public_site_url'], '/')

    def test_camper_cannot_call_staff_award_endpoint(self):
        from .activity_scoring_api import ActivityScoringView
        with patch('dic.activity_scoring_api.record_activity') as write:
            response = ActivityScoringView.as_view()(APIRequestFactory().post('/', {}, format='json'))
        self.assertIn(response.status_code, (401, 403))
        write.assert_not_called()

    def test_foreign_camper_score_lookup_stays_scoped(self):
        from .activity_scoring_api import CamperScoringView
        from rest_framework.exceptions import PermissionDenied
        with patch('dic.activity_scoring_api.authorized_grant', side_effect=PermissionDenied), \
             patch('dic.activity_scoring_api.camper_scores') as scores, \
             patch('dic.activity_scoring_api.transaction.atomic'):
            # Exercise the underlying authenticated handler without its DB transaction wrapper.
            with self.assertRaises(PermissionDenied):
                CamperScoringView.get.__wrapped__(CamperScoringView(), SimpleNamespace())
        scores.assert_not_called()

    def test_other_family_item_is_rejected_before_scoring_projection(self):
        from .activity_scoring_api import CamperScoringView
        from rest_framework.exceptions import NotFound
        request = SimpleNamespace(query_params={'item': '2'})
        lookup = MagicMock()
        lookup.select_related.return_value.first.return_value = None
        with patch('dic.activity_scoring_api.authorized_grant', return_value='synthetic-grant'), \
             patch('dic.activity_scoring_api.scoped_orders', return_value=[SimpleNamespace(pk=1)]), \
             patch('dic.activity_scoring_api.RegistrationOrderItem.objects.filter', return_value=lookup) as query, \
             patch('dic.activity_scoring_api.camper_scores') as scores:
            with self.assertRaises(NotFound):
                CamperScoringView.get.__wrapped__(CamperScoringView(), request)
        query.assert_called_once_with(pk=2, order_id__in=[1])
        scores.assert_not_called()
