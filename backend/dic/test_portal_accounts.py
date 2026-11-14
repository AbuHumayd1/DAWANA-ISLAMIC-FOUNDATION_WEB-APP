"""Database-free account and OAuth policies; mocks never establish acceptance."""
import logging
import inspect
import io
import socket
import ssl
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError, APIException
from rest_framework.test import APIRequestFactory
from . import portal_accounts as accounts
from . import portal_google as google
from .portal_account_api import PasswordLoginView, PasswordResetView, AccountActivateView, GoogleCallbackView
from .portal_auth_logging import OAuthCallbackFilter
from .security import digest_value


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, DIC_GOOGLE_CLIENT_ID='synthetic-client')
class PortalAccountPolicyTests(SimpleTestCase):
    def test_exchange_exception_type_diagnostic_uses_fixed_labels_only(self):
        for cls in (ModuleNotFoundError, ImportError, TypeError, AttributeError, ValueError, NameError, KeyError, RuntimeError, PermissionError):
            with self.subTest(cls=cls.__name__):
                self.assertEqual(google.exchange_exception_type(cls('private-secret')), cls.__name__)
        custom = type('PrivateClientIdAndSecret', (RuntimeError,), {})
        self.assertEqual(google.exchange_exception_type(custom('private-code')), 'OtherException')

    def test_exchange_http_error_cleanup_cannot_hide_provider_status(self):
        error = HTTPError(google.TOKEN_URL, 401, 'private-secret', {}, io.BytesIO(b'{"error":"invalid_client"}'))
        error.close = MagicMock(side_effect=RuntimeError('private-cleanup-details'))
        with patch.object(google, 'urlopen', side_effect=error):
            with self.assertRaises(google.OAuthExchangeFailure) as caught:
                google.exchange_token(b'private-payload')
        self.assertEqual((caught.exception.category, caught.exception.http_status), ('invalid_client', 401))

    def test_exchange_http_errors_use_only_allowlisted_provider_identifiers(self):
        for value, expected in (('invalid_client', 'invalid_client'), ('invalid_grant', 'invalid_grant'),
                ('redirect_uri_mismatch', 'redirect_uri_mismatch'), ('private-secret', 'oauth_http_error')):
            body = ('{"error":"'+value+'","error_description":"private-code-and-secret"}').encode()
            error = HTTPError(google.TOKEN_URL, 400, 'private-reason', {}, io.BytesIO(body))
            with self.subTest(value=value), patch.object(google, 'urlopen', side_effect=error):
                with self.assertRaises(google.OAuthExchangeFailure) as caught: google.exchange_token(b'private-payload')
            self.assertEqual((caught.exception.category, caught.exception.http_status), (expected, 400))
            self.assertNotIn('private-', str(caught.exception))

    def test_exchange_malformed_http_error_body_preserves_only_status(self):
        for body in (b'private-non-json-body', b'[]', b'x'*65537):
            error = HTTPError(google.TOKEN_URL, 502, 'private-reason', {}, io.BytesIO(body))
            with self.subTest(size=len(body)), patch.object(google, 'urlopen', side_effect=error):
                with self.assertRaises(google.OAuthExchangeFailure) as caught: google.exchange_token(b'payload')
            self.assertEqual((caught.exception.category, caught.exception.http_status), ('oauth_http_error', 502))

    def test_exchange_distinguishes_timeout_tls_dns_and_connection_errors(self):
        for reason, expected in ((TimeoutError('private-timeout'), 'timeout'), (ssl.SSLError('private-tls'), 'tls_error'),
                (socket.gaierror('private-host'), 'dns_error'), (ConnectionError('private-host'), 'connection_error'),
                ('private-network-reason', 'connection_error')):
            with self.subTest(expected=expected), patch.object(google, 'urlopen', side_effect=URLError(reason)):
                with self.assertRaises(google.OAuthExchangeFailure) as caught: google.exchange_token(b'payload')
            self.assertEqual((caught.exception.category, caught.exception.http_status), (expected, 0))

    def test_exchange_rejects_malformed_oversized_and_missing_id_tokens(self):
        for body in (b'not-json', b'\xff', b'[]', b'null', b'{}', b'{"id_token":""}', b'{"id_token":123}', b'x'*(1024*1024+1)):
            response = MagicMock(); response.status = 200; response.read.return_value = body
            with self.subTest(size=len(body)), patch.object(google, 'urlopen') as open_request:
                open_request.return_value.__enter__.return_value = response
                with self.assertRaises(google.OAuthExchangeFailure) as caught: google.exchange_token(b'payload')
            self.assertEqual((caught.exception.category, caught.exception.http_status), ('malformed_token_response', 200))

    def test_exchange_valid_response_returns_token_for_existing_signature_validation(self):
        response = MagicMock(); response.status = 200; response.read.return_value = b'{"id_token":"synthetic-unverified-token"}'
        with patch.object(google, 'urlopen') as open_request:
            open_request.return_value.__enter__.return_value = response
            self.assertEqual(google.exchange_token(b'payload'), 'synthetic-unverified-token')
        self.assertEqual(open_request.call_args.kwargs, {'timeout': 10})
        response.read.assert_called_once_with(1024*1024+1)

    @override_settings(DIC_PORTAL_FRONTEND_URL='https://portal.example.invalid/dic/participant')
    def test_callback_exchange_diagnostic_is_sanitized_and_local_exceptions_are_generic(self):
        for error, expected in ((google.OAuthExchangeFailure('invalid_client', 401), 'category=invalid_client http_status=401'),
                (google.OAuthExchangeFailure('private-secret', 'private-code'), 'category=local_application_error http_status=0'),
                (RuntimeError('private-secret'), 'category=local_application_error http_status=0 exception_type=RuntimeError'),
                (ImportError('private-module-name'), 'category=local_application_error http_status=0 exception_type=ImportError'),
                (TypeError('private-arguments'), 'category=local_application_error http_status=0 exception_type=TypeError')):
            def fail(request, report_stage):
                report_stage('token_exchange'); raise error
            with self.subTest(expected=expected), patch.object(google, 'complete', side_effect=fail), self.assertLogs('dic.portal_oauth', level='WARNING') as logs:
                response = GoogleCallbackView.as_view()(APIRequestFactory().get('/callback/', {'code': 'private-code'}))
            self.assertIn(expected, logs.output[0]); self.assertNotIn('private-', str(logs.output))
            self.assertEqual(response.status_code, 302); self.assertNotIn('dawana_participant', response.cookies)

    @override_settings(DIC_PORTAL_FRONTEND_URL='https://portal.example.invalid/dic/participant')
    def test_callback_diagnoses_failures_without_logging_secrets_or_exception_details(self):
        for stage in ('state_verification', 'token_exchange', 'id_token_validation', 'claim_validation', 'account_unlinked', 'account_linking', 'session_eligibility'):
            def fail(request, report_stage):
                report_stage(stage)
                raise AuthenticationFailed('private-token-and-identity')
            with self.subTest(stage=stage), patch.object(google, 'complete', side_effect=fail), self.assertLogs('dic.portal_oauth', level='WARNING') as logs:
                response = GoogleCallbackView.as_view()(APIRequestFactory().get('/callback/', {'code': 'private-code', 'state': 'private-state'}))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].endswith('#signin=failed'))
            self.assertNotIn('dawana_participant', response.cookies)
            self.assertIn('stage='+stage, logs.output[0])
            self.assertNotIn('private-', str(logs.output))

    @override_settings(DIC_PORTAL_FRONTEND_URL='https://portal.example.invalid/dic/participant')
    def test_callback_stage_log_rejects_nonconstant_values(self):
        def fail(request, report_stage):
            report_stage('private-code-or-provider-error')
            raise ValueError('private-secret')
        with patch.object(google, 'complete', side_effect=fail), self.assertLogs('dic.portal_oauth', level='WARNING') as logs:
            GoogleCallbackView.as_view()(APIRequestFactory().get('/callback/'))
        self.assertIn('stage=unknown', logs.output[0]); self.assertNotIn('private-', str(logs.output))

    def test_disabled_rollout_requires_no_schema_or_database(self):
        with override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=False):
            self.assertIsNone(accounts.account_session(NS()))
            with self.assertRaises(APIException): accounts.require_accounts()

    @override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=False)
    def test_disabling_accounts_cannot_downgrade_account_cookie_into_otp_scope(self):
        from .participant_api import authorized_grant, COOKIE
        with patch.object(accounts.ParticipantPortalGrant.objects, 'filter') as query:
            with self.assertRaises(AuthenticationFailed):
                authorized_grant(NS(COOKIES={COOKIE: accounts.ACCOUNT_TOKEN_PREFIX+'synthetic'}))
        query.assert_not_called()

    def test_password_strength_and_django_hashing(self):
        user = get_user_model()(username='guardian')
        for password in ('', 'x' * 129):
            with self.subTest(password=password), self.assertRaises(ValidationError): accounts.password_policy(password, user)
        for password in ('a', 'password', '123456789012', 'short', ' ', 'a b!', '  leading trailing  '):
            accounts.password_policy(password, user)
        password = 'River-Cedar!Sparrow-84'
        accounts.password_policy(password, user); user.set_password(password)
        self.assertNotEqual(user.password, password); self.assertTrue(user.check_password(password)); self.assertFalse(user.check_password('wrong'))

    def test_staff_superuser_and_inactive_accounts_are_not_camper_credentials(self):
        for active, staff, superuser in ((False, False, False), (True, True, False), (True, False, True)):
            self.assertFalse(accounts.usable(NS(user=NS(is_active=active, is_staff=staff, is_superuser=superuser))))

    def test_wrong_and_unknown_password_use_same_generic_error(self):
        user = get_user_model()(username='guardian'); user.set_password('River-Cedar!Sparrow-84')
        for account in (None, NS(user=user)):
            with patch.object(accounts.PortalAccount.objects, 'select_related') as query:
                query.return_value.filter.return_value.first.return_value = account
                with self.assertRaisesMessage(AuthenticationFailed, accounts.INVALID): accounts.password_account('guardian', 'wrong')

    def test_login_throttle_precedes_password_authentication(self):
        request = APIRequestFactory().post('/login/', {'identifier': 'guardian', 'password': 'wrong'}, format='json')
        with patch.object(accounts, 'require_accounts'), patch.object(accounts, 'rate_limit', side_effect=PermissionDenied('limited')) as limit, patch.object(accounts, 'password_account') as authenticate:
            response = PasswordLoginView.as_view()(request)
        self.assertEqual(response.status_code, 403); limit.assert_called_once(); authenticate.assert_not_called()

    def test_login_cannot_accept_caller_permissions_or_booking_scope(self):
        for field in ('is_staff', 'order_id', 'participant_id', 'payment_status', 'expires_at'):
            with self.subTest(field=field), patch.object(accounts, 'require_accounts'), patch.object(accounts, 'password_account') as authenticate:
                response = PasswordLoginView.as_view()(APIRequestFactory().post('/login/', {'identifier': 'guardian', 'password': 'wrong', field: 'true'}, format='json'))
                self.assertEqual(response.status_code, 400); authenticate.assert_not_called()

    def test_setup_cannot_accept_privilege_or_payment_overrides(self):
        with patch.object(accounts, 'activate') as activate:
            response = AccountActivateView.as_view()(APIRequestFactory().post('/activate/', {'username': 'guardian', 'password': 'a-long-password', 'is_staff': True}, format='json'))
        self.assertEqual(response.status_code, 400); activate.assert_not_called()

    def test_password_reset_never_accepts_target_account_identifier(self):
        with patch.object(accounts, 'require_accounts'), patch.object(accounts, 'reset_password') as reset:
            response = PasswordResetView.as_view()(APIRequestFactory().post('/reset/', {'password': 'a-long-password', 'identifier': 'foreign'}, format='json'))
        self.assertEqual(response.status_code, 400); reset.assert_not_called()

    def test_old_otp_cannot_change_credentials(self):
        grant = NS(created_at=timezone.now()-timedelta(minutes=11))
        with patch('dic.participant_api.authorized_grant', return_value=grant), patch('dic.participant_api.scoped_orders') as scope:
            with self.assertRaises(PermissionDenied): accounts.fresh_otp(NS())
        scope.assert_not_called()

    def test_password_or_google_session_is_not_fresh_otp_for_recovery(self):
        grant = NS(created_at=timezone.now())
        with patch('dic.participant_api.authorized_grant', return_value=grant), patch.object(accounts.PortalAccountSession.objects, 'filter') as query:
            query.return_value.exists.return_value = True
            with self.assertRaises(PermissionDenied): accounts.fresh_otp(NS())

    def test_fresh_otp_still_requires_existing_payment_or_tutor_eligibility(self):
        grant = NS(created_at=timezone.now())
        with patch('dic.participant_api.authorized_grant', return_value=grant), patch.object(accounts.PortalAccountSession.objects, 'filter') as query, patch('dic.participant_api.scoped_orders', return_value=[NS()]), patch.object(accounts, 'booking_eligible', return_value=False):
            query.return_value.exists.return_value = False
            with self.assertRaises(PermissionDenied): accounts.fresh_otp(NS())

    def test_explicit_bindings_and_eligibility_control_access_not_receipt_email(self):
        account = NS(contact_channel='email', contact_digest='verified')
        bindings = [NS(order=NS(pk=i)) for i in range(3)]
        with patch.object(accounts.PortalAccountBooking.objects, 'filter') as query, patch(
                'dic.participant_api.primary_contact_matches') as contact, patch.object(
                accounts, 'booking_eligible', side_effect=[True, False, True]):
            query.return_value.select_related.return_value = bindings
            result = accounts.linked_orders(account)
            self.assertIs(query.call_args.kwargs['account'], account)
            self.assertTrue(query.call_args.kwargs['revoked_at__isnull'])
            contact.assert_not_called()
        self.assertEqual([order.pk for order in result], [0, 2])

    def test_reset_credential_version_and_revoked_google_link_invalidate_sessions(self):
        user = NS(is_active=True, is_staff=False, is_superuser=False)
        account = NS(user=user, credential_version=2)
        for version, method, google_linked in ((1, 'password', True), (2, 'google', False)):
            with self.subTest(method=method), patch.object(accounts.PortalAccountSession.objects, 'select_related') as query, patch.object(accounts.PortalGoogleLink.objects, 'filter') as links:
                query.return_value.filter.return_value.first.return_value = NS(account=account, credential_version=version, method=method)
                links.return_value.exists.return_value = google_linked
                with self.assertRaises(AuthenticationFailed): accounts.account_session(NS())

    def test_google_subject_is_identity_and_email_changes_do_not_rebind(self):
        claims = {'iss': 'https://accounts.google.com', 'aud': 'synthetic-client', 'sub': 'stable-subject', 'nonce': 'nonce', 'email_verified': True, 'email': 'changed@example.invalid'}
        self.assertEqual(google.check_claims(claims, digest_value('nonce')), 'stable-subject')

    def test_google_nonce_issuer_audience_authorized_party_and_subject_are_required(self):
        claims = {'iss': 'https://accounts.google.com', 'aud': 'synthetic-client', 'sub': 'stable', 'nonce': 'nonce', 'email_verified': True}
        for field, value in (('iss', 'https://evil.invalid'), ('aud', 'other-client'), ('azp', 'other-client'), ('nonce', 'wrong'), ('sub', ''), ('email_verified', 'true')):
            with self.subTest(field=field), self.assertRaises(AuthenticationFailed): google.check_claims({**claims, field: value}, digest_value('nonce'))

    def test_oauth_attempt_requires_browser_state_expiry_and_single_use(self):
        now = timezone.now()
        attempt = NS(consumed_at=None, expires_at=now+timedelta(minutes=1), state_digest=digest_value('state'), browser_digest=digest_value('browser'))
        self.assertTrue(google.attempt_valid(attempt, 'state', 'browser', now))
        for state, browser in (('foreign', 'browser'), ('state', 'foreign'), ('state', '')):
            self.assertFalse(google.attempt_valid(attempt, state, browser, now))
        self.assertFalse(google.attempt_valid(attempt, 'state', 'browser', now+timedelta(minutes=2)))
        attempt.consumed_at = now
        self.assertFalse(google.attempt_valid(attempt, 'state', 'browser', now))

    def test_pkce_uses_rfc7636_s256_vector(self):
        self.assertEqual(google.challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')

    @override_settings(DEBUG=False)
    def test_production_callback_requires_https_and_exact_fixed_path(self):
        for url in ('http://127.0.0.1'+google.CALLBACK_PATH, 'https://example.invalid/elsewhere', 'https://user@example.invalid'+google.CALLBACK_PATH, 'https://example.invalid'+google.CALLBACK_PATH+'?next=evil'):
            self.assertFalse(google.safe_url(url, google.CALLBACK_PATH))
        self.assertTrue(google.safe_url('https://example.invalid'+google.CALLBACK_PATH, google.CALLBACK_PATH))

    def test_callback_logs_redact_codes_and_exceptions(self):
        record = logging.LogRecord('django.server', logging.INFO, '', 0, 'GET /api/v1/dic/participant/auth/google/callback/?code=secret&state=secret', (), None)
        OAuthCallbackFilter().filter(record)
        self.assertNotIn('secret', record.getMessage())

    def test_oauth_signature_library_is_required_not_client_claims(self):
        with patch.object(google.importlib.util, 'find_spec', return_value=None): self.assertFalse(google.google_available())

    def test_fresh_guardian_otp_authorizes_only_its_verified_orders(self):
        grant = NS(created_at=timezone.now()); orders = [NS(pk=7), NS(pk=8)]
        with patch('dic.participant_api.authorized_grant', return_value=grant), patch.object(accounts.PortalAccountSession.objects, 'filter') as query, patch('dic.participant_api.scoped_orders', return_value=orders), patch.object(accounts, 'booking_eligible', return_value=True):
            query.return_value.exists.return_value = False
            self.assertEqual(accounts.fresh_otp(NS()), (grant, orders))

    def test_password_reset_requires_fresh_proof_and_updates_hash_version_and_sessions(self):
        user = get_user_model()(username='guardian'); user.save = MagicMock()
        account = NS(user=user, credential_version=4, save=MagicMock())
        password = 'River-Cedar!Sparrow-84'
        with patch.object(accounts, 'require_accounts'), patch.object(accounts, 'fresh_otp', return_value=(NS(channel='email'), [NS(pk=7)])) as proof, patch.object(accounts, 'owned_account', return_value=account), patch.object(accounts.ParticipantPortalGrant.objects, 'filter') as grants, patch.object(accounts, 'audit'):
            inspect.unwrap(accounts.reset_password)(NS(), password)
        proof.assert_called_once(); self.assertTrue(user.check_password(password))
        self.assertEqual(account.credential_version, 5)
        grants.assert_called_once_with(portalaccountsession__account=account)
        grants.return_value.update.assert_called_once()

    def test_reset_between_password_check_and_session_issue_cannot_create_session(self):
        initial = NS(pk=1, credential_version=1)
        current = NS(credential_version=2, user=NS(is_active=True, is_staff=False, is_superuser=False))
        with patch.object(accounts.PortalAccount.objects, 'select_for_update') as rows, patch.object(accounts, 'linked_orders') as orders:
            rows.return_value.select_related.return_value.get.return_value = current
            with self.assertRaises(AuthenticationFailed): inspect.unwrap(accounts.issue_session)(initial, NS(), 'password')
        orders.assert_not_called()

    def test_account_session_scope_intersects_explicit_booking_bindings(self):
        from .participant_api import scoped_orders
        candidates = [NS(pk=7, registration_basis='paid'), NS(pk=8, registration_basis='paid')]
        with patch('dic.participant_api.RegistrationOrder.objects.filter') as rows, patch.object(accounts, 'account_session', return_value=NS(account=NS())), patch.object(accounts, 'linked_orders', return_value=[candidates[0]]), patch('dic.participant_api.primary_contact_matches', return_value=True):
            rows.return_value.exclude.return_value.select_related.return_value = candidates
            self.assertEqual(scoped_orders(NS(channel='email', contact_digest='proof')), [candidates[0]])

    def test_unlinked_google_subject_cannot_use_matching_email_to_create_account(self):
        import pathlib
        source = pathlib.Path(google.__file__).read_text(encoding='utf-8')
        self.assertIn("filter(subject=subject, revoked_at__isnull=True)", source)
        self.assertNotIn('login_email=', source)
        self.assertNotIn('PortalAccount.objects.create', source)
