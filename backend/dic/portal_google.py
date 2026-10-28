"""Server-only Google code flow. Email claims never confer booking access."""
import base64
import hashlib
import hmac
import http.client
import importlib.util
import json
import secrets
import socket
import ssl
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from .models import PortalOAuthAttempt, PortalGoogleLink
from .security import digest_value
from . import portal_accounts as accounts

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
OAUTH_COOKIE = 'dawana_portal_oauth'
CALLBACK_PATH = '/api/v1/dic/participant/auth/google/callback/'
FAILURE_STAGES = frozenset(('configuration', 'state_verification', 'provider_response',
    'token_exchange', 'id_token_validation', 'claim_validation', 'account_linking',
    'account_lookup', 'account_unlinked', 'session_eligibility'))
EXCHANGE_CATEGORIES = frozenset(('invalid_client', 'invalid_grant', 'redirect_uri_mismatch',
    'oauth_http_error', 'connection_error', 'timeout', 'tls_error', 'dns_error',
    'malformed_token_response', 'local_application_error'))


def exchange_diagnostic(category, status):
    return (category if isinstance(category, str) and category in EXCHANGE_CATEGORIES else 'local_application_error',
        status if type(status) is int and 100 <= status <= 599 else 0)


class OAuthExchangeFailure(AuthenticationFailed):
    def __init__(self, category, status=0):
        self.category, self.http_status = exchange_diagnostic(category, status)
        super().__init__(accounts.INVALID)


def exchange_exception_type(error):
    # Never use a dynamic class name: even custom exception names are untrusted.
    for cls, label in ((OAuthExchangeFailure, 'OAuthExchangeFailure'),
            (ModuleNotFoundError, 'ModuleNotFoundError'), (ImportError, 'ImportError'),
            (TypeError, 'TypeError'), (AttributeError, 'AttributeError'),
            (UnicodeEncodeError, 'UnicodeEncodeError'), (UnicodeDecodeError, 'UnicodeDecodeError'),
            (ValueError, 'ValueError'), (UnboundLocalError, 'UnboundLocalError'),
            (NameError, 'NameError'), (KeyError, 'KeyError'), (RuntimeError, 'RuntimeError'),
            (PermissionError, 'PermissionError'), (OSError, 'OSError')):
        if type(error) is cls:
            return label
    return 'OtherException'


def network_category(error):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)): return 'timeout'
    if isinstance(reason, ssl.SSLError): return 'tls_error'
    if isinstance(reason, socket.gaierror): return 'dns_error'
    return 'connection_error'


@sensitive_variables()
def exchange_token(payload):
    """Bounded response handling; provider text never becomes a log message."""
    status = 0
    try:
        with urlopen(Request(TOKEN_URL, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}), timeout=10) as response:
            status = response.status
            data = response.read(1024*1024+1)
    except HTTPError as error:
        category = 'oauth_http_error'
        try:
            # Read only to classify an exact allowlisted OAuth error identifier.
            data = error.read(65537)
            body = json.loads(data) if len(data) <= 65536 else None
            value = body.get('error') if isinstance(body, dict) else None
            if isinstance(value, str) and value in ('invalid_client', 'invalid_grant', 'redirect_uri_mismatch'):
                category = value
        except Exception:
            pass  # Malformed HTTP error bodies retain the status, never their text.
        finally:
            try:
                error.close()
            except Exception:
                pass  # Cleanup must not mask the already-known Google HTTP status.
        raise OAuthExchangeFailure(category, error.code) from None
    except (URLError, OSError, http.client.HTTPException) as error:
        raise OAuthExchangeFailure(network_category(error), status) from None
    if len(data) > 1024*1024:
        raise OAuthExchangeFailure('malformed_token_response', status)
    try:
        body = json.loads(data)
    except (ValueError, UnicodeError):
        raise OAuthExchangeFailure('malformed_token_response', status) from None
    token = body.get('id_token') if isinstance(body, dict) else None
    if not isinstance(token, str) or not token or len(token) > 32768:
        raise OAuthExchangeFailure('malformed_token_response', status)
    return token


def safe_url(value, path):
    try:
        url = urlsplit(value)
        secure = url.scheme == 'https' or (settings.DEBUG and url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1'))
        return bool(secure and url.hostname and not url.username and not url.password and not url.query and not url.fragment and url.path == path)
    except ValueError:
        return False


def google_available():
    try:
        library = importlib.util.find_spec('google.oauth2.id_token') is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        library = False
    return bool(accounts.enabled() and library and getattr(settings, 'DIC_GOOGLE_CLIENT_ID', '')
        and getattr(settings, 'DIC_GOOGLE_CLIENT_SECRET', '')
        and safe_url(getattr(settings, 'DIC_GOOGLE_REDIRECT_URI', ''), CALLBACK_PATH)
        and safe_url(getattr(settings, 'DIC_PORTAL_FRONTEND_URL', ''), '/dic/participant'))


def require_google():
    accounts.require_accounts()
    if not google_available():
        raise PermissionDenied('Google sign-in is not configured. Use a password or verification code.')


def cipher():
    key = hmac.new(settings.SECRET_KEY.encode(), b'dic.portal.oauth.pkce.v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


def check_claims(claims, nonce_digest):
    # Called only AFTER google-auth verifies signature, issuer, audience and times.
    client = settings.DIC_GOOGLE_CLIENT_ID
    subject = claims.get('sub')
    if (claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
            or claims.get('aud') != client or claims.get('azp', client) != client
            or claims.get('email_verified') is not True
            or not isinstance(subject, str) or not 1 <= len(subject) <= 255
            or not isinstance(claims.get('nonce'), str)
            or not secrets.compare_digest(digest_value(claims['nonce']), nonce_digest)):
        raise AuthenticationFailed(accounts.INVALID)
    return subject


def attempt_valid(attempt, state, browser, now):
    return bool(attempt and not attempt.consumed_at and attempt.expires_at > now
        and browser and secrets.compare_digest(attempt.state_digest, digest_value(state))
        and secrets.compare_digest(attempt.browser_digest, digest_value(browser)))


@sensitive_variables()
def start(request, intent, remember):
    require_google()
    from .portal_phase3 import session_seconds
    session_seconds(remember)
    if intent not in ('login', 'link'): raise PermissionDenied(accounts.INVALID)
    grant = None
    with transaction.atomic():
        if intent == 'link':
            grant, orders = accounts.fresh_otp(request)
            accounts.owned_account(grant, orders)
        state, nonce, browser, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
        PortalOAuthAttempt.objects.create(state_digest=digest_value(state), nonce_digest=digest_value(nonce),
            browser_digest=digest_value(browser), encrypted_verifier=cipher().encrypt(verifier.encode()).decode(),
            intent=intent, grant=grant, remember_device=remember, expires_at=timezone.now()+timedelta(minutes=10))
    url = AUTH_URL + '?' + urlencode({'client_id': settings.DIC_GOOGLE_CLIENT_ID,
        'redirect_uri': settings.DIC_GOOGLE_REDIRECT_URI, 'response_type': 'code', 'scope': 'openid email',
        'state': state, 'nonce': nonce, 'code_challenge': challenge(verifier), 'code_challenge_method': 'S256',
        'prompt': 'select_account'})
    return url, browser


@sensitive_variables()
def exchange(code, verifier, nonce_digest, report_stage=lambda stage: None):
    report_stage('token_exchange')
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest
    payload = urlencode({'code': code, 'client_id': settings.DIC_GOOGLE_CLIENT_ID,
        'client_secret': settings.DIC_GOOGLE_CLIENT_SECRET, 'redirect_uri': settings.DIC_GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code', 'code_verifier': verifier}).encode()
    token = exchange_token(payload)
    report_stage('id_token_validation')
    transport = GoogleRequest()
    def bounded_request(*args, **kwargs):
        kwargs['timeout'] = 10
        return transport(*args, **kwargs)
    claims = id_token.verify_oauth2_token(token, bounded_request, audience=settings.DIC_GOOGLE_CLIENT_ID)
    report_stage('claim_validation')
    return check_claims(claims, nonce_digest)


@sensitive_variables()
def complete(request, report_stage=lambda stage: None):
    report_stage('configuration')
    require_google()
    report_stage('state_verification')
    if len(request.query_params.getlist('state')) != 1 or len(request.query_params.getlist('code')) > 1:
        raise AuthenticationFailed(accounts.INVALID)
    state = request.query_params.get('state', '')
    browser = request.COOKIES.get(OAUTH_COOKIE, '')
    if len(state) > 256 or len(browser) > 256: raise AuthenticationFailed(accounts.INVALID)
    # Commit consumption BEFORE provider I/O. A failed exchange cannot replay.
    with transaction.atomic():
        attempt = PortalOAuthAttempt.objects.select_for_update().filter(state_digest=digest_value(state)).first()
        if not attempt_valid(attempt, state, browser, timezone.now()): raise AuthenticationFailed(accounts.INVALID)
        verifier = cipher().decrypt(attempt.encrypted_verifier.encode()).decode()
        attempt.consumed_at = timezone.now(); attempt.encrypted_verifier = ''
        attempt.save(update_fields=['consumed_at', 'encrypted_verifier'])
    report_stage('provider_response')
    code = request.query_params.get('code', '')
    if request.query_params.get('error') or not code or len(code) > 8192:
        raise AuthenticationFailed(accounts.INVALID)
    subject = exchange(code, verifier, attempt.nonce_digest, report_stage=report_stage)
    with transaction.atomic():
        if attempt.intent == 'link':
            report_stage('account_linking')
            grant, orders = accounts.fresh_otp(request)
            if grant.pk != attempt.grant_id: raise PermissionDenied(accounts.INVALID)
            account = accounts.owned_account(grant, orders)
            existing = PortalGoogleLink.objects.filter(account=account).first()
            if existing and existing.subject != subject: raise PermissionDenied(accounts.INVALID)
            try:
                with transaction.atomic():
                    link, _ = PortalGoogleLink.objects.get_or_create(subject=subject, defaults={'account': account})
                    if link.account_id != account.pk: raise PermissionDenied(accounts.INVALID)
                    link.revoked_at = None; link.save(update_fields=['revoked_at'])
            except IntegrityError:
                raise PermissionDenied(accounts.INVALID)
            accounts.audit(account, 'google_linked')
        else:
            report_stage('account_lookup')
            link = PortalGoogleLink.objects.select_related('account__user').filter(subject=subject, revoked_at__isnull=True).first()
            if not link:
                report_stage('account_unlinked')
                raise AuthenticationFailed(accounts.INVALID)
            account = link.account
        report_stage('session_eligibility')
        return accounts.issue_session(account, request, 'google', attempt.remember_device)
