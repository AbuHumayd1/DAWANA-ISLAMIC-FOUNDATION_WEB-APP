"""CSRF-protected participant credentials; never creates a Django staff session."""
import logging
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .participant_api import PortalView, authorized_grant, cookie, COOKIE
from . import portal_accounts as accounts
from . import portal_google as google
from .models import PortalGoogleLink, ParticipantPortalGrant


class Credentials(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    remember_device = serializers.BooleanField(default=False)


class Activation(serializers.Serializer):
    username = serializers.CharField(max_length=40)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirmation = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    email = serializers.EmailField()

    def validate(self, data):
        import secrets
        if not secrets.compare_digest(data['password'].encode(), data['password_confirmation'].encode()):
            raise serializers.ValidationError({'password_confirmation': 'Passwords must match.'})
        data.pop('password_confirmation')
        return data


def values(serializer, request):
    form = serializer(data=request.data)
    form.is_valid(raise_exception=True)
    if set(request.data) - set(form.fields): raise serializers.ValidationError('Unexpected account fields.')
    return form.validated_data


def session_response(result):
    grant, token, seconds = result
    response = Response({'authenticated': True, 'expires_at': grant.expires_at})
    cookie(response, COOKIE, token, seconds)
    return response


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class PasswordLoginView(PortalView):
    throttle_scope = 'dic_participant_verify'

    def post(self, request):
        accounts.require_accounts()
        data = values(Credentials, request)
        accounts.rate_limit(request, data['identifier'], 'password')
        account = accounts.password_account(data['identifier'], data['password'])
        return session_response(accounts.issue_session(account, request, 'password', data['remember_device']))


class AccountStatusView(PortalView):
    def get(self, request):
        if not accounts.enabled(): return Response({'enabled': False})
        accounts.require_accounts()
        grant = authorized_grant(request)
        mapping = accounts.account_session(grant)
        if mapping:
            account, fresh = mapping.account, False
        else:
            with transaction.atomic():
                try:
                    proof, orders = accounts.fresh_otp(request)
                except PermissionDenied:
                    return Response({'enabled': True, 'fresh_otp': False, 'account': None})
                account = accounts.PortalAccount.objects.filter(contact_channel=proof.channel, contact_digest=proof.contact_digest,
                    bookings__order__in=orders, bookings__revoked_at__isnull=True).select_related('user').distinct().first()
                fresh = True
        from .registration_accounts import pending_registration
        visible = accounts.usable(account) or (fresh and account and grant.channel == 'email'
            and pending_registration(account))
        return Response({'enabled': True, 'fresh_otp': fresh, 'account': None if not visible else {
            'username': account.user.username, 'has_password': account.user.has_usable_password(),
            'google_linked': PortalGoogleLink.objects.filter(account=account, revoked_at__isnull=True).exists()}})


@method_decorator(sensitive_post_parameters('password', 'password_confirmation'), name='dispatch')
class AccountActivateView(PortalView):
    def post(self, request):
        data = values(Activation, request)
        accounts.require_accounts()
        accounts.rate_limit(request, data['username'], 'activate')
        account = accounts.activate(request, **data)
        return Response({'updated': True, 'username': account.user.username})


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class PasswordResetView(PortalView):
    def post(self, request):
        accounts.require_accounts()
        # Reset accepts only a new password; no caller-selected account identity.
        if set(request.data) != {'password'} or not isinstance(request.data['password'], str):
            raise serializers.ValidationError('Submit only a new password after booking verification.')
        from .security import digest_value
        accounts.rate_limit(request, digest_value(request.COOKIES.get(COOKIE, '')), 'reset')
        accounts.reset_password(request, request.data['password'])
        return Response({'updated': True})


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class AccountLinkBookingView(PortalView):
    def post(self, request):
        accounts.require_accounts()
        data = values(Credentials, request)
        accounts.rate_limit(request, data['identifier'], 'link-booking')
        accounts.link_booking(request, data['identifier'], data['password'])
        return Response({'updated': True})


class GoogleStart(serializers.Serializer):
    intent = serializers.ChoiceField(choices=['login', 'link'])
    remember_device = serializers.BooleanField(default=False)


class GoogleStartView(PortalView):
    def post(self, request):
        data = values(GoogleStart, request)
        google.require_google()
        accounts.rate_limit(request, request.META.get('REMOTE_ADDR', 'unknown'), 'google')
        url, browser = google.start(request, data['intent'], data['remember_device'])
        response = Response({'authorization_url': url})
        cookie(response, google.OAUTH_COOKIE, browser, 600)
        return response


class GoogleCallbackView(PortalView):
    def get(self, request):
        # Fixed configured destination only; fragment conveys no authentication.
        if not google.safe_url(settings.DIC_PORTAL_FRONTEND_URL, '/dic/participant'):
            raise PermissionDenied('Google callback is not configured.')
        stage = 'configuration'
        def report_stage(value):
            nonlocal stage
            stage = value if value in google.FAILURE_STAGES else 'unknown'
        try:
            result = google.complete(request, report_stage=report_stage)
        except Exception as error:
            # No provider tokens, query strings or exception details in logs/UI.
            logger = logging.getLogger('dic.portal_oauth')
            if stage == 'token_exchange':
                category, status = google.exchange_diagnostic(
                    error.category if isinstance(error, google.OAuthExchangeFailure) else 'local_application_error',
                    error.http_status if isinstance(error, google.OAuthExchangeFailure) else 0)
                logger.warning('Participant OAuth failed: stage=token_exchange category=%s http_status=%s exception_type=%s',
                    category, status, google.exchange_exception_type(error))
            else:
                logger.warning('Participant OAuth failed: stage=%s', stage)
            response = HttpResponseRedirect(settings.DIC_PORTAL_FRONTEND_URL + '#signin=failed')
        else:
            grant, token, seconds = result
            response = HttpResponseRedirect(settings.DIC_PORTAL_FRONTEND_URL + '#signin=complete')
            cookie(response, COOKIE, token, seconds)
        response.delete_cookie(google.OAUTH_COOKIE, path='/api/v1/dic/participant/', samesite='Lax')
        response['Referrer-Policy'] = 'no-referrer'
        return response


class GoogleUnlinkView(PortalView):
    def post(self, request):
        accounts.require_accounts()
        with transaction.atomic():
            grant, orders = accounts.fresh_otp(request)
            account = accounts.owned_account(grant, orders)
            if not account.user.has_usable_password():
                raise PermissionDenied('Set a password using verified recovery before unlinking Google.')
            PortalGoogleLink.objects.filter(account=account, revoked_at__isnull=True).update(revoked_at=timezone.now())
            account.credential_version += 1; account.save(update_fields=['credential_version'])
            ParticipantPortalGrant.objects.filter(portalaccountsession__account=account).update(revoked_at=timezone.now())
            accounts.audit(account, 'google_unlinked')
        return Response({'updated': True})


class EmailVerifyInput(serializers.Serializer):
    token = serializers.CharField(max_length=2048, trim_whitespace=False, write_only=True)


@method_decorator(sensitive_post_parameters(), name='dispatch')
class EmailVerifyView(PortalView):
    def post(self, request):
        from .registration_accounts import verify_email
        data = values(EmailVerifyInput, request)
        accounts.rate_limit(request, request.META.get('REMOTE_ADDR', 'unknown'), 'email-verify')
        verify_email(data['token'])
        return Response({'verified': True, 'detail': 'Email verified. Sign in with your email and password when your booking is eligible. Ordinary registrations require verified payment; authorized complimentary tutors do not.'})


@method_decorator(sensitive_post_parameters(), name='dispatch')
class EmailResendView(PortalView):
    def post(self, request):
        from .registration_accounts import credential_account, schedule_verification, require_verification_delivery
        from rest_framework.exceptions import AuthenticationFailed
        accounts.require_accounts()
        require_verification_delivery()
        data = values(Credentials, request)
        accounts.rate_limit(request, data['identifier'], 'email-resend')
        try:
            account = credential_account(data['identifier'], data['password'])
            if not account.user.is_active: schedule_verification(account)
        except Exception:
            pass
        return Response({'detail': 'If these credentials identify an account awaiting verification, an email has been requested.'}, status=202)
