"""Verified immediate gateway addresses; fail closed without trusting chains."""
from ipaddress import ip_address, ip_network
from django.conf import settings
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


def resolved_client(meta, gateways):
    peer = ip_address(meta.get('REMOTE_ADDR', ''))
    trusted = any(peer in ip_network(network, strict=True) for network in gateways)
    if trusted:
        # One gateway-generated address, never a client-controlled chain.
        return str(ip_address(meta.get('HTTP_X_DAWANA_CLIENT_IP', ''))), True
    return str(peer), False


class TrustedGatewayMiddleware(MiddlewareMixin):
    def process_request(self, request):
        try:
            address, trusted = resolved_client(request.META, getattr(settings, 'DAWANA_TRUSTED_GATEWAYS', []))
        except ValueError:
            return HttpResponse('Gateway configuration requires review.', status=400)
        request.META['REMOTE_ADDR'] = address
        request.META.pop('HTTP_X_FORWARDED_FOR', None)
        request.META.pop('HTTP_X_DAWANA_CLIENT_IP', None)
        if not trusted:
            request.META.pop('HTTP_X_FORWARDED_PROTO', None)

    def process_response(self, request, response):
        if request.path.startswith(('/api/', '/admin/')):
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
        return response


class AdminLoginThrottleMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.method != 'POST' or request.path.rstrip('/') != '/admin/login':
            return None
        from dic.portal_accounts import rate_limit
        from dic.recovery_views import RecoveryRateLimited
        from django.db import DatabaseError
        # Same atomic, durable counters as recovery. Hashing occurs in rate_limit;
        # neither passwords nor raw identifiers are persisted by this middleware.
        # Pair the account with the verified IP to prevent remote account lockout.
        identity = str(request.POST.get('username', '')).strip().casefold()[:254]
        try:
            rate_limit(request, identity + ':' + request.META.get('REMOTE_ADDR', ''), 'admin-login')
        except RecoveryRateLimited:
            response = HttpResponse('Please wait before trying to sign in again.', status=429)
            response['Retry-After'] = '3600'
            return response
        except DatabaseError:
            return HttpResponse('Administrative sign-in is temporarily unavailable.', status=503)
