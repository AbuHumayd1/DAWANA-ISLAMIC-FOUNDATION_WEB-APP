from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from django.http import HttpResponse
from .request_security import resolved_client, TrustedGatewayMiddleware, AdminLoginThrottleMiddleware


class GatewaySecurityTests(SimpleTestCase):
    def test_untrusted_forwarding_cannot_change_client(self):
        meta = {'REMOTE_ADDR': '192.0.2.3', 'HTTP_X_FORWARDED_FOR': '198.51.100.4',
                'HTTP_X_DAWANA_CLIENT_IP': '198.51.100.5'}
        self.assertEqual(resolved_client(meta, ['127.0.0.1/32']), ('192.0.2.3', False))

    def test_verified_gateway_requires_single_valid_address(self):
        meta = {'REMOTE_ADDR': '127.0.0.1', 'HTTP_X_DAWANA_CLIENT_IP': '192.0.2.9'}
        self.assertEqual(resolved_client(meta, ['127.0.0.1/32']), ('192.0.2.9', True))
        for value in ('', '192.0.2.9, 198.51.100.1', 'spoof'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolved_client({**meta, 'HTTP_X_DAWANA_CLIENT_IP': value}, ['127.0.0.1/32'])

    def test_untrusted_scheme_and_chain_are_removed_and_private_response_not_cached(self):
        request = RequestFactory().get('/api/v1/health/', HTTP_X_FORWARDED_FOR='spoof',
                                      HTTP_X_FORWARDED_PROTO='https')
        middleware = TrustedGatewayMiddleware(lambda r: HttpResponse())
        with self.settings(DAWANA_TRUSTED_GATEWAYS=[]):
            middleware.process_request(request)
        self.assertNotIn('HTTP_X_FORWARDED_FOR', request.META)
        self.assertNotIn('HTTP_X_FORWARDED_PROTO', request.META)
        self.assertIn('no-store', middleware.process_response(request, HttpResponse())['Cache-Control'])

    def test_admin_throttle_uses_real_durable_boundary_without_authentication_bypass(self):
        from dic.recovery_views import RecoveryRateLimited
        middleware = AdminLoginThrottleMiddleware(lambda r: HttpResponse())
        request = RequestFactory().post('/admin/login/', {'username': 'staff', 'password': 'synthetic'})
        with patch('dic.portal_accounts.rate_limit') as limit:
            self.assertIsNone(middleware.process_request(request))
            self.assertEqual(limit.call_args.args[2], 'admin-login')
            self.assertNotIn('synthetic', str(limit.call_args))
            limit.side_effect = RecoveryRateLimited()
            self.assertEqual(middleware.process_request(request).status_code, 429)

    def test_admin_get_and_non_login_post_are_not_throttled_here(self):
        middleware = AdminLoginThrottleMiddleware(lambda r: HttpResponse())
        with patch('dic.portal_accounts.rate_limit') as limit:
            middleware.process_request(RequestFactory().get('/admin/login/'))
            middleware.process_request(RequestFactory().post('/api/v1/health/'))
            limit.assert_not_called()
