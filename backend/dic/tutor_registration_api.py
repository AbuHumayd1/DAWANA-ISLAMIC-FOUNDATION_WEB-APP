"""Browser-bound tutor invitation verification; never accepts a public role claim."""
import secrets
import uuid
from datetime import timedelta
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .participant_api import PortalView
from .models import TutorRegistrationAuthorization, TutorVerification
from .serializers import ParticipantInputSerializer, StrictSerializer
from .security import digest_value
from .recovery import channel_available, send_recovery_code, RecoveryDeliveryError
from .recovery_views import _consume_request_limits, _code_digest
from .tutor_registration import valid_invitation, redeem, audit
from rest_framework import serializers

COOKIE = 'dawana_tutor_browser'
CAPABILITY = 'dawana_tutor_capability'
PATH = '/api/v1/dic/tutor-registration/'
INVALID = 'Tutor invitation verification is unavailable. Ask your administrator for assistance.'


def set_cookie(response, request, name, value):
    response.set_cookie(name, value, max_age=600, httponly=True, secure=request.is_secure(), samesite='Strict', path=PATH)


class TutorParticipantInput(ParticipantInputSerializer):
    # Reuse all normal participant fields without letting clients select a category.
    category_id = None


class ChallengeInput(StrictSerializer):
    invitation = serializers.RegexField(r'^[A-Za-z0-9_-]{43}$')


class VerifyInput(StrictSerializer):
    verification_id = serializers.UUIDField()
    code = serializers.RegexField(r'^[0-9]{6}$')


class RedeemInput(StrictSerializer):
    verification_id = serializers.UUIDField()
    participant = TutorParticipantInput()


class TutorChallengeView(PortalView):
    throttle_scope = 'dic_participant_request'

    def get(self, request):
        return Response({'csrfToken': get_token(request)})

    def post(self, request):
        data = ChallengeInput(data=request.data); data.is_valid(raise_exception=True)
        auth = TutorRegistrationAuthorization.objects.select_related('edition').filter(
            invitation_digest=digest_value(data.validated_data['invitation'])).first()
        # Same shape for absent/expired/revoked invitations; no identity disclosed.
        response = Response({'verification_id': str(uuid.uuid4()), 'detail': 'If this invitation is available, a code will be sent to its authorized email.'}, status=202)
        browser = secrets.token_urlsafe(32)
        set_cookie(response, request, COOKIE, browser)
        if not valid_invitation(auth):
            return response
        _consume_request_limits('email', auth.email, request, timezone.now())
        if not channel_available('email'):
            return response
        code = f'{secrets.randbelow(1000000):06d}'
        with transaction.atomic():
            auth = TutorRegistrationAuthorization.objects.select_for_update(of=('self',)).select_related('edition').get(pk=auth.pk)
            if not valid_invitation(auth):
                return response
            verification = TutorVerification.objects.create(authorization=auth,
                invitation_digest=auth.invitation_digest, browser_digest=digest_value(browser),
                code_digest='', expires_at=timezone.now() + timedelta(minutes=10))
            verification.code_digest = _code_digest(verification.pk, code)
            verification.save(update_fields=['code_digest'])
            audit(auth, None, 'verification_requested', verification=str(verification.pk))
        try:
            send_recovery_code('email', auth.email, code)
        except RecoveryDeliveryError:
            TutorVerification.objects.filter(pk=verification.pk).update(code_digest='')
        response.data['verification_id'] = str(verification.pk)
        return response


class TutorVerifyView(PortalView):
    throttle_scope = 'dic_participant_verify'

    def post(self, request):
        data = VerifyInput(data=request.data); data.is_valid(raise_exception=True)
        now, capability, edition = timezone.now(), None, None
        with transaction.atomic():
            row = TutorVerification.objects.select_for_update(of=('self',)).select_related('authorization__edition').filter(pk=data.validated_data['verification_id']).first()
            if row and not row.verified_at and row.attempts < 5 and row.expires_at > now:
                row.attempts += 1
                if (valid_invitation(row.authorization, now)
                    and row.invitation_digest == row.authorization.invitation_digest
                    and secrets.compare_digest(row.browser_digest, digest_value(request.COOKIES.get(COOKIE, '')))
                    and row.code_digest and secrets.compare_digest(row.code_digest, _code_digest(row.pk, data.validated_data['code']))):
                    capability = secrets.token_urlsafe(32)
                    row.capability_digest = digest_value(capability)
                    row.verified_at, row.expires_at = now, now + timedelta(minutes=10)
                    row.code_digest = ''
                    edition = row.authorization.edition
                    audit(row.authorization, None, 'contact_verified', verification=str(row.pk))
                row.save(update_fields=['attempts', 'capability_digest', 'verified_at', 'expires_at', 'code_digest'])
        # Failed attempts must commit, rather than being rolled back by the error.
        if not capability:
            raise ValidationError(INVALID)
        response = Response({'verified': True, 'name': row.authorization.intended_name,
            'email': row.authorization.email, 'edition': {'name': edition.name,
                'camp_start_date': edition.camp_start_date, 'camp_end_date': edition.camp_end_date, 'venue': edition.venue_name}})
        set_cookie(response, request, CAPABILITY, capability)
        return response


class TutorRedeemView(PortalView):
    throttle_scope = 'dic_participant_verify'

    def post(self, request):
        data = RedeemInput(data=request.data); data.is_valid(raise_exception=True)
        try:
            order = redeem(data.validated_data['verification_id'], request.COOKIES.get(COOKIE, ''),
                request.COOKIES.get(CAPABILITY, ''), data.validated_data['participant'])
        except TutorVerification.DoesNotExist:
            raise ValidationError(INVALID)
        return Response({'registration_basis': 'tutor', 'payment_status': 'not_required',
            'status': order.status, 'order_id': str(order.public_id), 'total_amount_ngn': '0.00',
            'portal_path': '/dic/participant'})
