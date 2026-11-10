"""Database-free credential creation and one-time email proof regressions."""
import inspect
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from django.core import signing
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import APIException, ValidationError, AuthenticationFailed
from . import registration_accounts as registration
from . import portal_accounts as accounts
from .serializers import RegistrationCredentialsSerializer
from .views import _request_fingerprint


class RegistrationAccountPolicyTests(SimpleTestCase):
    @override_settings(DEBUG=False, DEFAULT_FROM_EMAIL='', RESEND_API_KEY='',
                       EMAIL_BACKEND='config.https_email.EmailBackend')
    def test_missing_verification_delivery_returns_503_before_queue_write_or_send(self):
        with patch.object(registration.PortalAccount.objects, 'filter') as rows, \
                patch.object(registration, 'send_mail') as send:
            for operation in (registration.schedule_verification, registration.deliver_verification):
                with self.assertRaises(APIException) as error:
                    operation(NS(pk=1))
                self.assertEqual(error.exception.status_code, 503)
        rows.assert_not_called()
        send.assert_not_called()
        from .portal_account_api import EmailResendView
        with patch.object(accounts, 'require_accounts'):
            with self.assertRaises(APIException) as error:
                EmailResendView().post(NS())
        self.assertEqual(error.exception.status_code, 503)

    @override_settings(DEBUG=False, DEFAULT_FROM_EMAIL='sender@example.test', RESEND_API_KEY='synthetic-only',
                       EMAIL_BACKEND='config.https_email.EmailBackend', DIC_RECOVERY_ENCRYPTION_KEY='',
                       DIC_AUTOMATION_ACTOR_ID=0,
                       DIC_PORTAL_EMAIL_VERIFY_URL='https://foundation.example.test/dic/participant')
    def test_signed_verification_delivery_does_not_require_otp_encryption_or_housing_actor(self):
        account = self.account()
        account.login_email = account.user.email
        with patch.object(registration, 'send_mail', return_value=1) as send:
            registration.deliver_verification(account)
        send.assert_called_once()
        self.assertFalse(account.user.is_active)

    @override_settings(DEBUG=False, DEFAULT_FROM_EMAIL='sender@example.test')
    def test_test_email_backends_cannot_fake_production_verification_delivery(self):
        for backend in ('console', 'locmem', 'dummy'):
            with self.subTest(backend=backend), \
                    override_settings(EMAIL_BACKEND='django.core.mail.backends.' + backend + '.EmailBackend'), \
                    self.assertRaises(APIException):
                registration.require_verification_delivery()

    def test_password_and_confirmation_are_required_and_strength_checked(self):
        password = 'River-Cedar!Sparrow-84'
        form = RegistrationCredentialsSerializer(data={'password': password, 'password_confirmation': password})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.validated_data, {'password': password})
        self.assertEqual(form.data, {})
        for data in ({}, {'password': password}, {'password': password, 'password_confirmation': 'different'},
                {'password': '123456789012', 'password_confirmation': '123456789012'}):
            self.assertFalse(RegistrationCredentialsSerializer(data=data).is_valid())

    def test_passwords_do_not_enter_order_fingerprints(self):
        common = {'participants': [], 'primary_registrant': {'email': 'synthetic@example.test'}}
        self.assertEqual(_request_fingerprint(common), _request_fingerprint({**common, 'portal_account': {'password': 'private-password'}}))

    @override_settings(DEBUG=False, DIC_PORTAL_EMAIL_VERIFY_URL='http://example.test/dic/participant')
    def test_email_link_requires_fixed_https_production_destination(self):
        with self.assertRaises(ValidationError): registration.verification_url()
        with override_settings(DIC_PORTAL_EMAIL_VERIFY_URL='https://example.test/dic/participant'):
            self.assertEqual(registration.verification_url(), 'https://example.test/dic/participant')

    def account(self):
        user = get_user_model()(username='synthetic', email='synthetic@example.test', is_active=False)
        user.set_password('River-Cedar!Sparrow-84'); user.save = MagicMock()
        return NS(pk=1, credential_version=1, contact_digest='synthetic-contact', user=user)

    def test_one_time_email_proof_never_issues_portal_session(self):
        account = self.account(); token = registration.email_token(account)
        with patch.object(registration.accounts, 'require_accounts'), patch.object(registration.PortalAccount.objects, 'select_for_update') as rows, patch.object(registration, 'pending_registration', return_value=True), patch.object(accounts, 'audit') as audit, patch.object(accounts, 'issue_session') as issue:
            rows.return_value.select_related.return_value.get.return_value = account
            inspect.unwrap(registration.verify_email)(token)
        self.assertTrue(account.user.is_active); account.user.save.assert_called_once_with(update_fields=['is_active'])
        audit.assert_called_once(); issue.assert_not_called()

    def test_replayed_changed_password_or_credential_version_email_proof_is_rejected(self):
        for change in ('already_verified', 'version', 'password'):
            account = self.account(); token = registration.email_token(account)
            if change == 'version': account.credential_version += 1
            if change == 'password': account.user.set_password('Another-River!Cedar-84')
            with self.subTest(change=change), patch.object(accounts, 'require_accounts'), patch.object(registration.PortalAccount.objects, 'select_for_update') as rows, patch.object(registration, 'pending_registration', return_value=change != 'already_verified'):
                rows.return_value.select_related.return_value.get.return_value = account
                with self.assertRaises(ValidationError): inspect.unwrap(registration.verify_email)(token)
                account.user.save.assert_not_called()

    def test_invalid_or_expired_signature_cannot_activate_account(self):
        for error in (signing.BadSignature(), signing.SignatureExpired()):
            with patch.object(accounts, 'require_accounts'), patch.object(signing, 'loads', side_effect=error), patch.object(registration.PortalAccount.objects, 'select_for_update') as rows:
                with self.assertRaises(ValidationError): inspect.unwrap(registration.verify_email)('synthetic-invalid-token')
                rows.assert_not_called()

    def test_existing_email_requires_password_before_order_binding(self):
        account = self.account()
        with patch.object(accounts, 'require_accounts'), patch.object(registration.PortalAccount.objects, 'select_for_update') as rows, patch.object(registration, 'credential_account', side_effect=AuthenticationFailed()), patch.object(registration.PortalAccountBooking.objects, 'get_or_create') as binding:
            rows.return_value.select_related.return_value.filter.return_value.first.return_value = account
            order = NS(primary_registrant=NS(email='synthetic@example.test'))
            with self.assertRaises(AuthenticationFailed): inspect.unwrap(registration.bind_registration)(order, {'password': 'wrong-password'})
            binding.assert_not_called()

    def test_verified_or_legacy_disabled_accounts_are_not_pending_registrations(self):
        account = self.account(); account.user.is_active = True
        with patch.object(registration.DICAdminAuditEvent.objects, 'filter') as events:
            self.assertFalse(registration.pending_registration(account))
        account.user.is_active = False
        with patch.object(registration.DICAdminAuditEvent.objects, 'filter') as events:
            events.return_value.filter.return_value.exists.return_value = False
            self.assertFalse(registration.pending_registration(account))
