"""Strict portal authorization policies. Database access is prohibited."""
import inspect
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, AuthenticationFailed
from rest_framework.test import APIRequestFactory
from . import participant_api as portal
from . import portal_accounts as accounts
from .portal_account_api import Activation
from .security import digest_value
from .serializers import PrimaryRegistrantInputSerializer, RegistrationOrderCreateSerializer


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=False)
class PortalEligibilityPolicyTests(SimpleTestCase):
    def test_password_authentication_without_eligible_orders_cannot_issue_a_session(self):
        account = NS(pk=1, credential_version=1, user=NS(is_active=True, is_staff=False, is_superuser=False))
        with patch.object(accounts.PortalAccount.objects, 'select_for_update') as rows, patch.object(accounts, 'linked_orders', return_value=[]), patch.object(accounts.ParticipantPortalGrant.objects, 'create') as create:
            rows.return_value.select_related.return_value.get.return_value = account
            with self.assertRaises(AuthenticationFailed): inspect.unwrap(accounts.issue_session)(account, NS(), 'password')
        create.assert_not_called()

    def test_otp_scopes_exclude_unpaid_failed_refunded_and_cancelled_orders(self):
        for state in ('pending', 'failed', 'refunded', 'cancelled', 'abandoned'):
            orders = [NS(pk=1, registration_basis='paid', state='verified'), NS(pk=2, registration_basis='paid', state=state)]
            with self.subTest(state=state), patch.object(portal.RegistrationOrder.objects, 'filter') as rows, patch.object(portal, 'primary_contact_matches', return_value=True), patch.object(accounts, 'booking_eligible', side_effect=lambda order: order.state == 'verified'):
                rows.return_value.exclude.return_value.select_related.return_value = orders
                self.assertEqual(portal.scoped_orders(NS(channel='email', contact_digest='proof')), [orders[0]])

    def test_every_protected_grant_requires_a_current_eligible_scope(self):
        for view in (portal.PortalMeView, portal.PortalEnrollmentsView):
            with self.subTest(view=view.__name__), patch.object(portal.ParticipantPortalGrant.objects, 'filter') as rows, patch.object(portal, 'scoped_orders', return_value=[]), patch.object(portal, 'record') as record:
                rows.return_value.first.return_value = NS()
                request = APIRequestFactory().get('/protected/')
                request.COOKIES[portal.COOKIE] = 'synthetic-otp-cookie'
                response = view.as_view()(request)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('orders', response.data); record.assert_not_called()

    def test_existing_otp_session_loses_access_when_payment_changes(self):
        request = NS(COOKIES={portal.COOKIE: 'synthetic-otp-cookie'})
        grant = NS()
        with patch.object(portal.ParticipantPortalGrant.objects, 'filter') as rows, patch.object(portal, 'scoped_orders', side_effect=[[NS()], []]):
            rows.return_value.first.return_value = grant
            self.assertIs(portal.authorized_grant(request), grant)
            with self.assertRaises(PermissionDenied): portal.authorized_grant(request)

    def test_unpaid_otp_verification_never_creates_a_portal_session(self):
        challenge = NS(pk=uuid4(), consumed_at=None, expires_at=timezone.now()+timedelta(minutes=5), attempts=0,
            browser_digest=digest_value('browser'), delivery_status='sent', code_digest='digest', order_id=1,
            channel='email', contact_digest='contact', save=MagicMock())
        with patch.object(portal.transaction, 'atomic'), patch.object(portal.ParticipantPortalChallenge.objects, 'select_for_update') as challenges, patch.object(portal.RegistrationOrder.objects, 'select_related') as orders, patch.object(portal, '_code_digest', return_value='digest'), patch.object(portal, 'primary_contact_matches', return_value=True), patch.object(accounts, 'booking_eligible', return_value=False), patch.object(portal.ParticipantPortalGrant.objects, 'create') as create, patch.object(portal, 'record'):
            challenges.return_value.filter.return_value.first.return_value = challenge
            orders.return_value.filter.return_value.exclude.return_value.first.return_value = NS()
            request = APIRequestFactory().post('/verify/', {'challenge_id': str(challenge.pk), 'code': '123456'}, format='json')
            request.COOKIES[portal.BROWSER_COOKIE] = 'browser'
            response = portal.PortalVerifyView.as_view()(request)
        self.assertEqual(response.status_code, 400); create.assert_not_called()

    def test_whole_order_requires_trusted_eligibility_for_every_child(self):
        items = [NS(pk=1, participant_id=uuid4()), NS(pk=2, participant_id=uuid4())]
        order = NS(status='confirmed', edition_id=1, items=NS(all=lambda: items))
        for approved, expected in (([True, True], True), ([True, False], False)):
            with self.subTest(approved=approved), patch.object(accounts.CampEnrollment.objects, 'filter') as rows, patch('dic.participant_services.eligibility', side_effect=[{'eligible': value} for value in approved]) as eligibility:
                rows.return_value.first.return_value = None
                self.assertEqual(accounts.booking_eligible(order), expected)
                self.assertEqual(eligibility.call_count, 2)

    def test_source_registration_must_be_complete_before_eligibility_lookup(self):
        for state in ('submitted', 'cancelled'):
            with self.subTest(state=state), patch('dic.participant_services.eligibility') as eligibility:
                self.assertFalse(accounts.booking_eligible(NS(status=state)))
                eligibility.assert_not_called()

    def test_foreign_child_remains_denied_even_with_an_eligible_sibling_order(self):
        with patch.object(portal, 'authorized_grant', return_value=NS()), patch.object(portal, 'scoped_orders', return_value=[NS(pk=7)]), patch.object(portal.CampEnrollment.objects, 'filter') as enrollments:
            enrollments.return_value.select_related.return_value.first.return_value = None
            from rest_framework.exceptions import NotFound
            with self.assertRaises(NotFound): portal.scoped_enrollment(NS(), uuid4())
            self.assertEqual(enrollments.call_args.kwargs['source_item__order_id__in'], [7])

    def test_primary_contact_requires_explicit_name_and_email(self):
        for data in ({}, {'full_name': 'Guardian'}, {'email': 'guardian@example.test'}, {'full_name': 'Guardian', 'email': ''}):
            self.assertFalse(PrimaryRegistrantInputSerializer(data=data).is_valid())
        form = PrimaryRegistrantInputSerializer(data={'full_name': 'Guardian', 'email': ' GUARDIAN@example.test '})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.validated_data['email'], 'guardian@example.test')
        self.assertTrue(RegistrationOrderCreateSerializer().fields['primary_registrant'].required)
        from .assisted_registration import AssistedPrimaryContact
        legacy = AssistedPrimaryContact(data={'full_name': 'Guardian', 'phone': '08012345678'})
        self.assertTrue(legacy.is_valid(), legacy.errors)

    def test_activation_requires_matching_password_confirmation_and_email(self):
        valid = {'username': 'guardian', 'email': 'guardian@example.test', 'password': 'River-Cedar!Sparrow-84', 'password_confirmation': 'River-Cedar!Sparrow-84'}
        form = Activation(data=valid); self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('password_confirmation', form.validated_data)
        for change in ({'password_confirmation': 'different'}, {'password_confirmation': ''}, {'email': ''}, {'password': ''}):
            with self.subTest(change=change): self.assertFalse(Activation(data={**valid, **change}).is_valid())

    def test_new_account_cannot_use_phone_proof_or_someone_elses_email(self):
        from .recovery_views import _contact_digest
        for channel in ('sms', 'email'):
            proof = NS(channel=channel, contact_digest=_contact_digest('email', 'owner@example.test'))
            with self.subTest(channel=channel), patch.object(accounts, 'require_accounts'), patch.object(accounts, 'fresh_otp', return_value=(proof, [NS()])), patch.object(accounts, 'get_user_model') as users:
                with self.assertRaises(PermissionDenied):
                    inspect.unwrap(accounts.activate)(NS(), 'guardian', 'River-Cedar!Sparrow-84', 'someoneelse@example.test')
                users.assert_not_called()

    def test_logout_remains_available_without_eligible_registration(self):
        with patch.object(portal.transaction, 'atomic'), patch.object(portal, 'authorized_grant', side_effect=PermissionDenied()) as authorize, patch.object(portal.ParticipantPortalGrant.objects, 'filter') as rows, patch.object(portal, 'record'):
            request = APIRequestFactory().post('/logout/', {}, format='json')
            request.COOKIES[portal.COOKIE] = 'synthetic-expired-cookie'
            response = portal.PortalLogoutView.as_view()(request)
        self.assertEqual(response.status_code, 204); authorize.assert_not_called()
        rows.return_value.update.assert_called_once()

    def test_tutor_exception_is_delegated_to_existing_eligibility_rules(self):
        order = NS(status='confirmed', registration_basis='tutor', edition_id=1,
            items=NS(all=lambda: [NS(pk=1, participant_id=uuid4())]))
        with patch.object(accounts.CampEnrollment.objects, 'filter') as rows, patch('dic.participant_services.eligibility', return_value={'eligible': True, 'code': 'authorized_tutor'}) as eligibility:
            rows.return_value.first.return_value = NS()
            self.assertTrue(accounts.booking_eligible(order)); eligibility.assert_called_once()
