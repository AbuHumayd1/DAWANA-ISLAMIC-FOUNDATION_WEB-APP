"""Schema-free Phase 3 regressions; SimpleTestCase prohibits database access."""
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory
from .portal_phase3 import capabilities, class_assignment, session_seconds
from .portal_continuation import PortalContinuationView, paid_continuation
from .participant_api import PortalIDView, scoped_enrollment, cookie


class PortalPhase3PolicyTests(SimpleTestCase):
    def request(self, data):
        return PortalContinuationView.as_view()(APIRequestFactory().post(
            '/api/v1/dic/participant/auth/continue/', data, format='json'))

    def test_session_default_and_explicit_personal_device_lifetime(self):
        self.assertEqual(session_seconds(), 1800)
        with override_settings(SESSION_COOKIE_AGE=28800): self.assertEqual(session_seconds(True), 28800)
        with override_settings(SESSION_COOKIE_AGE=86400): self.assertEqual(session_seconds(True), 28800)
        with override_settings(SESSION_COOKIE_AGE=900): self.assertEqual(session_seconds(True), 900)

    def test_session_policy_rejects_coerced_or_client_supplied_durations(self):
        for value in ('true', 'false', 1, 0, None, 86400):
            with self.subTest(value=value), self.assertRaises(ValidationError): session_seconds(value)

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_persistent_cookie_keeps_httponly_secure_samesite_and_scope(self):
        from django.http import HttpResponse
        response = HttpResponse()
        cookie(response, 'dawana_participant', 'synthetic-only', 28800)
        value = response.cookies['dawana_participant']
        self.assertTrue(value['secure']); self.assertTrue(value['httponly'])
        self.assertEqual(value['samesite'], 'Lax'); self.assertEqual(value['path'], '/api/v1/dic/participant/')
        self.assertEqual(value['max-age'], 28800)

    def test_google_is_explicitly_unavailable_without_linking_or_authentication(self):
        result = capabilities()
        self.assertFalse(result['google']['available'])
        self.assertNotIn('client_secret', str(result)); self.assertFalse(result['session']['sliding_refresh'])

    def test_category_and_tutor_registration_never_invent_classes(self):
        self.assertIsNone(class_assignment('paid')['name'])
        self.assertEqual(class_assignment('paid')['status'], 'pending_setup')
        self.assertEqual(class_assignment('tutor')['status'], 'not_applicable')

    def test_redirect_flags_email_and_oauth_claims_cannot_authorize_a_booking(self):
        for field in ('paid', 'status', 'email', 'google_sub', 'token', 'is_guardian', 'participant_id'):
            with self.subTest(field=field), patch('dic.portal_continuation.authorized_grant') as grant:
                response = self.request({'order_reference': str(uuid4()), field: 'trusted'})
                self.assertEqual(response.status_code, 400); grant.assert_not_called()

    def test_no_session_or_return_authority_cannot_authenticate(self):
        with patch('dic.portal_continuation.authorized_grant', side_effect=AuthenticationFailed()), patch(
                'dic.payment_return._session_digest', side_effect=NotFound()), patch(
                'dic.models.ParticipantPortalGrant.objects.create') as create:
            response = self.request({'order_reference': str(uuid4())})
        self.assertEqual(response.status_code, 404); create.assert_not_called()

    def test_expired_or_revoked_portal_session_still_requires_identity_verification(self):
        reference = uuid4()
        for reason in ('expired', 'revoked'):
            with self.subTest(reason=reason), patch('dic.portal_continuation.authorized_grant', side_effect=AuthenticationFailed(reason)), patch(
                    'dic.payment_return._session_digest', return_value='bound-browser'), patch(
                    'dic.payment_return._authorize', return_value=NS()), patch(
                    'dic.portal_continuation.paid_continuation', return_value=True):
                response = self.request({'order_reference': str(reference)})
                self.assertFalse(response.data['authenticated']); self.assertTrue(response.data['requires_verification'])
                self.assertNotIn('token', response.data)

    def test_existing_verified_exact_booking_session_is_reused_without_new_grant(self):
        reference = uuid4(); grant = NS(expires_at=timezone.now()+timedelta(minutes=10))
        with patch('dic.portal_continuation.authorized_grant', return_value=grant), patch(
                'dic.portal_continuation.scoped_orders', return_value=[NS(public_id=reference)]), patch(
                'dic.portal_continuation.paid_continuation', return_value=True), patch(
                'dic.models.ParticipantPortalGrant.objects.create') as create:
            response = self.request({'order_reference': str(reference)})
        self.assertTrue(response.data['authenticated']); create.assert_not_called()
        self.assertEqual(response.data['expires_at'], grant.expires_at.isoformat())

    def test_foreign_booking_is_not_linked_by_existing_session_or_email(self):
        with patch('dic.portal_continuation.authorized_grant', return_value=NS()), patch(
                'dic.portal_continuation.scoped_orders', return_value=[NS(public_id=uuid4())]), patch(
                'dic.payment_return._session_digest', side_effect=NotFound()), patch(
                'dic.models.ParticipantPortalScope.objects.create') as create:
            response = self.request({'order_reference': str(uuid4())})
        self.assertEqual(response.status_code, 404); create.assert_not_called()

    def test_unconfirmed_refunded_cancelled_or_tutor_order_is_not_paid_continuation(self):
        for changes in [dict(payment_status='pending'), dict(payment_status='refunded'), dict(status='cancelled'), dict(registration_basis='tutor')]:
            order = NS(**(dict(registration_basis='paid', status='confirmed', payment_status='paid') | changes))
            self.assertFalse(paid_continuation(order))

    def test_paid_flags_without_trusted_eligibility_evidence_do_not_suffice(self):
        order = NS(registration_basis='paid', status='confirmed', payment_status='paid', edition_id=1, items=MagicMock())
        order.items.all.return_value = [NS(pk=2, participant_id=uuid4())]
        with patch('dic.models.CampEnrollment.objects') as enrollments, patch('dic.portal_continuation.eligibility', return_value={'eligible': False}):
            enrollments.filter.return_value.first.return_value = None
            self.assertFalse(paid_continuation(order))

    def test_participant_lookup_is_limited_to_previously_authorized_bookings(self):
        request = NS(); enrollment_id = uuid4()
        with patch('dic.participant_api.authorized_grant', return_value=NS()), patch(
                'dic.participant_api.scoped_orders', return_value=[NS(pk=7)]), patch('dic.participant_api.CampEnrollment.objects') as rows:
            rows.filter.return_value.select_related.return_value.first.return_value = None
            with self.assertRaises(NotFound): scoped_enrollment(request, enrollment_id)
            self.assertEqual(rows.filter.call_args.kwargs['source_item__order_id__in'], [7])
            self.assertEqual(rows.filter.call_args.kwargs['pk'], enrollment_id)

    def test_child_id_json_uses_the_same_guardian_gate_as_card_downloads(self):
        with patch('dic.participant_api.authorized_portal_card', side_effect=PermissionDenied()), patch(
                'dic.participant_api.card_data') as card:
            response = PortalIDView.as_view()(APIRequestFactory().get('/'), enrollment_id=uuid4())
        self.assertEqual(response.status_code, 403); card.assert_not_called()

    def test_approved_housing_guardian_link_never_expands_verified_booking_scope(self):
        from datetime import date
        from .participant_api import authorized_portal_card
        child = NS(participant=NS(date_of_birth=date(2023, 1, 1)), edition=NS(),
            source_item=NS(order=NS(registration_basis='paid')))
        relation = NS(guardian=NS(), clean=MagicMock())
        for same_booking in (False, True):
            with self.subTest(same_booking=same_booking), patch('dic.participant_api.scoped_enrollment', return_value=(NS(), child)), patch(
                    'dic.participant_api.scoped_orders', return_value=[NS(pk=7)]), patch(
                    'dic.housing_policy.age_reference', return_value=date(2026, 12, 23)), patch(
                    'dic.housing_policy.age_on', return_value=3), patch('dic.models.GuardianRelationship.objects') as relationships, patch(
                    'dic.participant_api.CampEnrollment.objects') as enrollments, patch(
                    'dic.participant_api.eligibility', return_value={'eligible': True}):
                relationships.filter.return_value.select_related.return_value.first.return_value = relation
                enrollments.filter.return_value.select_related.return_value.first.return_value = NS() if same_booking else None
                if same_booking: self.assertIs(authorized_portal_card(NS(), uuid4()), child)
                else:
                    with self.assertRaises(PermissionDenied): authorized_portal_card(NS(), uuid4())
                self.assertEqual(enrollments.filter.call_args.kwargs['source_item__order_id__in'], [7])
                self.assertEqual(relationships.filter.call_args.kwargs['status'], 'approved')

    def test_foreign_child_is_denied_before_guardian_details_are_queried(self):
        from .participant_api import authorized_portal_card
        with patch('dic.participant_api.scoped_enrollment', side_effect=NotFound()), patch(
                'dic.models.GuardianRelationship.objects') as relationships:
            with self.assertRaises(NotFound): authorized_portal_card(NS(), uuid4())
        relationships.filter.assert_not_called()

    def test_continuation_requires_csrf_for_cookie_authority(self):
        request = APIRequestFactory(enforce_csrf_checks=True).post('/', {'order_reference': str(uuid4())}, format='json')
        with patch('dic.portal_continuation.authorized_grant') as grant:
            response = PortalContinuationView.as_view()(request)
        self.assertEqual(response.status_code, 403); grant.assert_not_called()
