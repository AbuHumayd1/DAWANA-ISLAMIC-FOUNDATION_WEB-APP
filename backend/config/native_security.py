"""Standard managed HTTPS, contingent on provider network/header guarantees."""
from django.conf import settings
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from ipaddress import ip_address


class ManagedHttpsMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.get_host()  # Validate even static responses short-circuited by WhiteNoise.
        if (not getattr(settings, 'ZEV_PROXY_HEADERS_VERIFIED', False)
                or request.META.get('HTTP_X_FORWARDED_PROTO') not in ('https', 'http')):
            return HttpResponse('Managed HTTPS ingress is not configured.', status=400)
        # The verified provider must strip XFF or include its real client address.
        # Only a single sanitized address is usable. Chains/invalid/absent values
        # retain the socket peer, giving conservative shared limits, never a guess.
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            try:
                request.META['REMOTE_ADDR'] = str(ip_address(forwarded))
            except ValueError:
                pass
        for name in ('HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'HTTP_FORWARDED',
                     'HTTP_X_FORWARDED_HOST', 'HTTP_X_DAWANA_CLIENT_IP'):
            request.META.pop(name, None)

    def process_response(self, request, response):
        if request.path.startswith(('/api/', '/admin/')):
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
        return response
