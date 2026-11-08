"""Standard managed HTTPS, contingent on provider network/header guarantees."""
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class ManagedHttpsMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.get_host()  # Validate even static responses short-circuited by WhiteNoise.
        if request.META.get('HTTP_X_FORWARDED_PROTO') not in ('https', 'http'):
            return HttpResponse('Managed HTTPS ingress is not configured.', status=400)
        # No client-IP forwarding contract is assumed. Keep the socket peer for
        # conservative shared throttles and discard all client identity headers.
        for name in ('HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'HTTP_FORWARDED',
                     'HTTP_X_FORWARDED_HOST', 'HTTP_X_DAWANA_CLIENT_IP'):
            request.META.pop(name, None)

    def process_response(self, request, response):
        if request.path.startswith(('/api/', '/admin/')):
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
        return response
