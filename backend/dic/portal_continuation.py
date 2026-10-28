"""Payment-return context is not proof of contact ownership; OTP remains required."""
from types import SimpleNamespace
import uuid
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.response import Response
from .participant_api import PortalView, authorized_grant, scoped_orders
from .participant_services import eligibility
from .portal_phase3 import capabilities


def paid_continuation(order):
    if order.registration_basis != 'paid' or order.status != 'confirmed' or order.payment_status != 'paid':
        return False
    items = list(order.items.all())
    if not items:
        return False
    from .models import CampEnrollment
    for item in items:
        enrollment = CampEnrollment.objects.filter(participant_id=item.participant_id,
            edition_id=order.edition_id, source_item_id=item.pk).first()
        candidate = enrollment or SimpleNamespace(source_item_id=item.pk, participant_id=item.participant_id,
            edition_id=order.edition_id, restriction_reason='', source_review_fingerprint='')
        if not eligibility(candidate)['eligible']:
            return False
    return True


class PortalCapabilitiesView(PortalView):
    def get(self, request):
        return Response(capabilities())


class PortalContinuationView(PortalView):
    def post(self, request):
        if not isinstance(request.data, dict) or set(request.data) != {'order_reference'}:
            raise ValidationError('Provide only the booking reference.')
        try:
            reference = uuid.UUID(str(request.data['order_reference']))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError('Provide a valid booking reference.')
        # Reuse only an already verified session with an existing exact booking scope.
        # Matching email, URL parameters and payment success flags cannot add scope.
        try:
            grant = authorized_grant(request)
        except AuthenticationFailed:
            grant = None
        if grant:
            order = next((row for row in scoped_orders(grant) if row.public_id == reference), None)
            if order is not None:
                if not paid_continuation(order):
                    raise PermissionDenied('Registration is not available for post-payment continuation.')
                return Response({'authenticated': True, 'expires_at': grant.expires_at.isoformat(),
                    'order_reference': str(reference)})
        # Existing browser-bound return authority can prefill recovery context, but
        # cannot mint a participant session. It is neither consumed nor extended.
        from .payment_return import _session_digest, _authorize
        order = _authorize(_session_digest(request), reference)
        if not paid_continuation(order):
            raise PermissionDenied('Registration is not available for post-payment continuation.')
        return Response({'authenticated': False, 'requires_verification': True,
            'order_reference': str(reference), 'message': 'Verify your registered primary contact to open this booking.'})
