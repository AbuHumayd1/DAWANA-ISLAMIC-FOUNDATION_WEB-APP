"""Narrow credential recovery and separately authorized financial decisions."""
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from .participant_api import PortalView, primary_contact_matches
from .portal_account_api import Credentials, values
from .operations_api import OperationsBaseView
from .models import PortalAccount, PortalAccountBooking, RegistrationOrder, PaymentAttempt
from . import portal_accounts as accounts
from . import order_lifecycle as lifecycle
from .security import new_order_access_token, order_access_token_expiry, digest_value
from .recovery_views import _order_recovery_summary


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class AccountOrderRecoveryView(PortalView):
    def post(self, request):
        accounts.require_accounts()
        data = values(Credentials, request)
        accounts.rate_limit(request, data['identifier'], 'recover-orders')
        account = accounts.password_account(data['identifier'], data['password'])
        version = account.credential_version
        result = []
        # This grants neither a participant dashboard nor a Django staff session.
        # Bound read/verify tokens remain usable for expired payment evidence.
        bindings = PortalAccountBooking.objects.filter(account=account, revoked_at__isnull=True,
            order__access_token_revoked_at__isnull=True, order__payment_status__in=('pending', 'failed'),
            order__status='submitted').order_by('-order__created_at', '-pk')[:100]
        for binding in bindings:
            with transaction.atomic():
                order = RegistrationOrder.objects.select_for_update(of=('self',)).select_related('primary_registrant', 'edition', 'current_price_revision').get(pk=binding.order_id)
                locked = PortalAccount.objects.select_for_update().select_related('user').get(pk=account.pk)
                current = PortalAccountBooking.objects.filter(pk=binding.pk, account=locked, revoked_at__isnull=True).exists()
                if not accounts.usable(locked) or locked.credential_version != version:
                    raise ValidationError(accounts.INVALID)
                if (not current or order.status == 'cancelled' or order.access_token_revoked_at
                        or not primary_contact_matches(order, locked.contact_channel, locked.contact_digest)):
                    continue
                # Paid bookings use the ordinary protected dashboard, not checkout recovery.
                if order.payment_status not in ('pending', 'failed'):
                    continue
                token = new_order_access_token()
                order.access_token_digest = digest_value(token)
                order.access_token_expires_at = order_access_token_expiry()
                order.save(update_fields=('access_token_digest', 'access_token_expires_at'))
                result.append(dict(order=_order_recovery_summary(order), access_token=token))
        accounts.audit(account, 'pending_orders_recovered', count=len(result))
        response = Response({'orders': result})
        response['Cache-Control'] = 'private, no-store'
        return response


class ResolutionInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    decision = serializers.ChoiceField(choices=('reinstate', 'refund_requested', 'refund_confirmed'))
    reason = serializers.CharField(max_length=1000, min_length=1)
    provider_refund_id = serializers.RegexField(r'^[0-9]{1,64}$', required=False, default='')


class PaymentResolutionView(OperationsBaseView):
    def get(self, request, reference):
        lifecycle.require_manager(request.user)
        attempt = PaymentAttempt.objects.filter(reference=reference).first()
        if not attempt:
            raise NotFound()
        return Response({'decisions': list(attempt.resolutions.order_by('created_at').values(
            'request_id', 'decision', 'reason', 'actor_id', 'created_at', 'provider_refund_id'))})

    def post(self, request, reference):
        lifecycle.require_manager(request.user)
        data = values(ResolutionInput, request)
        from .payment_resolution import resolve
        row = resolve(request.user, reference, **data)
        return Response({'decision': row.decision, 'request_id': row.request_id,
            'detail': 'Refund arranged; provider confirmation is still required.' if row.decision == 'refund_requested' else 'Decision recorded.'})
