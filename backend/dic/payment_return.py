"""Cookie-bound recovery of existing payments. Never initializes a charge."""
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.middleware.csrf import CsrfViewMiddleware
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .access import require_order_access
from .models import PaymentAttempt, PaymentReturnGrant, RegistrationOrder
from .payment_views import _verify_attempt, PaymentProviderUnavailable
from .payments import PaystackClient, PaystackConfigurationError

SESSION_MARKER = "dic_payment_return"
GRANT_TTL = timedelta(hours=2)
UNAVAILABLE = "This secure return session is unavailable. Recover the existing registration."


def _session_digest(request, create=False):
    session = request._request.session
    # Load the server-side session before trusting the cookie's session key.
    marker = session.get(SESSION_MARKER)
    if create and not marker:
        if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
            raise ValidationError("Server-side payment return sessions are unavailable.")
        session[SESSION_MARKER] = True
        session.save()
    if not session.get(SESSION_MARKER) or not session.session_key:
        raise NotFound(UNAVAILABLE)
    return salted_hmac("dic.payment-return.session", session.session_key, algorithm="sha256").hexdigest()


def _active_grants(digest):
    now = timezone.now()
    return PaymentReturnGrant.objects.select_related("order", "order__edition").filter(
        session_digest=digest, revoked_at__isnull=True, expires_at__gt=now,
        order__access_token_revoked_at__isnull=True, order__access_token_expires_at__gt=now,
    )


def _authorize(digest, order_id):
    grant = _active_grants(digest).filter(order__public_id=order_id).first()
    if not grant or not hmac.compare_digest(grant.access_digest, grant.order.access_token_digest):
        raise NotFound(UNAVAILABLE)
    return grant.order


def _summary(order):
    return {
        "order_id": str(order.public_id), "edition_name": order.edition.name,
        "payment_status": order.payment_status, "status": order.status,
        "total_amount_ngn": str(order.total_amount_ngn), "currency": "NGN",
        "participants": [
            {"name": item.participant.full_name, "category": item.category_name_snapshot,
             "occupation": item.participant.get_occupation_display(),
             "marital_status": item.participant.get_marital_status_display()}
            for item in order.items.select_related("participant").order_by("id")
        ],
    }


def _response(data):
    response = Response(data)
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["Vary"] = "Cookie"
    return response


class PaymentReturnThrottle(ScopedRateThrottle):
    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope, "60/hour")


class ReturnBaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PaymentReturnThrottle]
    throttle_scope = "dic_payment_return"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Cookie authority requires CSRF in every environment, independently of
        # the staging-only tester middleware and DRF's public bearer views.
        rejection = CsrfViewMiddleware(lambda req: None).process_view(request._request, lambda req: None, (), {})
        if rejection is not None:
            raise PermissionDenied("Payment return CSRF validation failed. Refresh and try again.")


class PaymentReturnGrantView(ReturnBaseView):
    def post(self, request, public_id):
        with transaction.atomic():
            order = RegistrationOrder.objects.select_for_update().filter(public_id=public_id).first()
            if not order:
                raise NotFound(UNAVAILABLE)
            require_order_access(request, order)
            digest = _session_digest(request, create=True)
            grant = PaymentReturnGrant.objects.filter(order=order, session_digest=digest).first()
            if grant and grant.revoked_at:
                raise NotFound(UNAVAILABLE)
            expires = min(timezone.now() + GRANT_TTL, request._request.session.get_expiry_date(), order.access_token_expires_at)
            PaymentReturnGrant.objects.update_or_create(
                order=order, session_digest=digest,
                defaults={"access_digest": order.access_token_digest, "expires_at": expires},
            )
        return _response({"ready": True, "expires_at": expires})


class ReturnLookupSerializer(serializers.Serializer):
    order_id = serializers.UUIDField(required=False)
    reference = serializers.CharField(required=False, max_length=80, trim_whitespace=False)


class PaymentReturnStatusView(ReturnBaseView):
    def post(self, request):
        digest = _session_digest(request)
        lookup = ReturnLookupSerializer(data=request.data)
        lookup.is_valid(raise_exception=True)
        values = lookup.validated_data
        public_id = values.get("order_id")
        reference = values.get("reference")
        attempt = None
        if reference:
            attempt = PaymentAttempt.objects.select_related("order").filter(reference=reference).first()
            if not attempt or (public_id and attempt.order.public_id != public_id):
                raise NotFound(UNAVAILABLE)
            public_id = attempt.order.public_id
        if not public_id:
            # Listing never calls Paystack. Only explicitly selected orders are
            # checked; a forged reference never falls back to another order.
            orders = [grant.order for grant in _active_grants(digest).order_by("-created_at")[:50]
                      if hmac.compare_digest(grant.access_digest, grant.order.access_token_digest)]
            return _response({"orders": [_summary(order) for order in orders]})
        order = _authorize(digest, public_id)
        unavailable = False
        if order.payment_status not in ("paid", "refunded") and order.status != "cancelled":
            if attempt is None:
                attempt = order.payment_attempts.order_by("-created_at", "-pk").first()
            if attempt:
                try:
                    _verify_attempt(attempt, PaystackClient())
                except (PaymentProviderUnavailable, PaystackConfigurationError):
                    unavailable = True
        # Recheck authority after external I/O; never return a stale paid draft.
        order = _authorize(digest, public_id)
        result = _summary(order)
        result["attempt_status"] = PaymentAttempt.objects.filter(pk=attempt.pk).values_list("status", flat=True).first() if attempt else None
        result["verification_unavailable"] = unavailable
        return _response({"order": result})
