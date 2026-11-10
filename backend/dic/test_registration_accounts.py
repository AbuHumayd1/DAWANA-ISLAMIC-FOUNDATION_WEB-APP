"""Database-free username, password and retired activation contract regressions."""
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from . import portal_accounts as accounts
from .serializers import RegistrationCredentialsSerializer
from .views import _request_fingerprint
from .portal_account_api import EmailVerifyView, EmailResendView, CredentialTransitionView


class RegistrationAccountPolicyTests(SimpleTestCase):
    @override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True)
    def test_username_cutover_refuses_missing_additive_schema(self):
        from rest_framework.exceptions import APIException
        existing = [model._meta.db_table for model in (accounts.PortalAccount,
            accounts.PortalAccountBooking, accounts.PortalAccountSession,
            accounts.PortalGoogleLink, accounts.PortalOAuthAttempt)]
        with patch.object(accounts.connection.introspection, 'table_names', return_value=existing):
            with self.assertRaises(APIException) as caught:
                accounts.require_accounts()
        self.assertEqual(caught.exception.status_code, 503)

    def test_username_normalization_and_reserved_names(self):
        self.assertEqual(accounts.normalize_username('  Camper.A-12  '), 'camper.a-12')
        for value in ('ab', 'a'*41, 'a@b.test', 'a/b', 'camper name', 'ADMIN', 'DIF', 'staff', 'dic_secret', 'école'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                accounts.normalize_username(value)

    def test_username_password_and_confirmation_are_required_and_strength_checked(self):
        password = 'River-Cedar!Sparrow-84'
        valid = {'username': ' Camper-84 ', 'password': password, 'password_confirmation': password}
        form = RegistrationCredentialsSerializer(data=valid)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.validated_data, {'username': 'camper-84', 'password': password})
        self.assertEqual(form.data, {})
        for change in ({'username': ''}, {'password_confirmation': 'different'}, {'password': '123456789012', 'password_confirmation': '123456789012'}):
            with self.subTest(change=change):
                self.assertFalse(RegistrationCredentialsSerializer(data={**valid, **change}).is_valid())
        for missing in valid:
            self.assertFalse(RegistrationCredentialsSerializer(data={k:v for k,v in valid.items() if k != missing}).is_valid())

    def test_passwords_do_not_enter_order_fingerprints(self):
        common = {'participants': [], 'primary_registrant': {'email': 'synthetic@example.test'}}
        self.assertEqual(_request_fingerprint(common), _request_fingerprint({**common,
            'portal_account': {'username': 'camper', 'password': 'private-password'}}))

    def test_public_signup_cannot_select_privileges_or_tutor_entitlement(self):
        valid = {'username': 'camper', 'password': 'River-Cedar!Sparrow-84', 'password_confirmation': 'River-Cedar!Sparrow-84'}
        for field in ('is_staff', 'is_superuser', 'is_active', 'registration_basis', 'payment_status'):
            with self.subTest(field=field):
                self.assertFalse(RegistrationCredentialsSerializer(data={**valid, field: True}).is_valid())

    @override_settings(DEBUG=False, DEFAULT_FROM_EMAIL='', RESEND_API_KEY='')
    def test_retired_email_endpoints_never_activate_or_send(self):
        for view in (EmailVerifyView, EmailResendView):
            with patch('django.core.mail.send_mail') as send:
                response = view.as_view()(APIRequestFactory().post('/retired/', {'token': 'old-link'}, format='json'))
                self.assertEqual(response.status_code, 410)
                send.assert_not_called()

    def test_transition_rejects_caller_selected_target_or_privilege(self):
        for field in ('account_id', 'order_id', 'is_staff', 'is_superuser'):
            with self.subTest(field=field), patch.object(accounts, 'require_accounts'), patch.object(accounts, 'rate_limit'), patch('dic.credential_transition.consume') as consume:
                response = CredentialTransitionView.as_view()(APIRequestFactory().post('/transition/', {
                    'token': 'x'*43, 'username': 'camper', 'password': 'River-Cedar!Sparrow-84',
                    'password_confirmation': 'River-Cedar!Sparrow-84', field: 'foreign'}, format='json'))
                self.assertEqual(response.status_code, 400)
                consume.assert_not_called()
