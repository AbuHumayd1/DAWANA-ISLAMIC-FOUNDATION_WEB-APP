from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
from io import BytesIO
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.http import HttpResponse, Http404
from django.core.exceptions import DisallowedHost
from django.urls import resolve, Resolver404
from .native_defaults import configure
from .native_security import ManagedHttpsMiddleware
from .spa import frontend, validate_frontend, static_headers


class NativeDeploymentTests(SimpleTestCase):
    def test_whitenoise_invokes_header_callback_for_html_and_assets(self):
        from whitenoise.middleware import WhiteNoiseMiddleware
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<html>React</html>', encoding='utf-8')
            (root / 'app.js').write_text('console.log("asset");', encoding='utf-8')
            with self.settings(WHITENOISE_ROOT=str(root), STATIC_ROOT=None,
                    WHITENOISE_ADD_HEADERS_FUNCTION=static_headers, WHITENOISE_MAX_AGE=0,
                    WHITENOISE_AUTOREFRESH=False):
                middleware = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
                for path in ('/index.html', '/app.js'):
                    response = middleware(RequestFactory().get(path))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['X-Frame-Options'], 'DENY')
                    if path.endswith('.html'):
                        self.assertEqual(response['Cache-Control'], 'no-store')
                    response.close()

    def test_defaults_keep_same_origin_full_workflow_and_live_collection_off(self):
        env = configure({'PUBLIC_HOST': 'foundation.example.test'})
        self.assertEqual(env['PAYSTACK_CALLBACK_URL'], 'https://foundation.example.test/dic/register/payment-return')
        self.assertEqual(env['DIC_PORTAL_EMAIL_VERIFY_URL'], 'https://foundation.example.test/dic/participant')
        self.assertEqual(env['DAWANA_WEBSITE_ONLY'], 'false')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertNotIn('ZEV_PROXY_HEADERS_VERIFIED', env)
        self.assertNotIn('TRUSTED_EDGE_CIDRS', env)

    @override_settings(ALLOWED_HOSTS=['foundation.example.test'], ZEV_PROXY_HEADERS_VERIFIED=True)
    def test_scheme_is_exact_and_unverified_identity_headers_are_ignored(self):
        middleware = ManagedHttpsMiddleware(lambda request: HttpResponse())
        request = RequestFactory().get('/', HTTP_HOST='foundation.example.test',
            HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_FOR='spoof', HTTP_X_REAL_IP='spoof')
        self.assertIsNone(middleware.process_request(request))
        self.assertNotIn('HTTP_X_FORWARDED_FOR', request.META)
        self.assertNotIn('HTTP_X_REAL_IP', request.META)
        request.META['HTTP_X_FORWARDED_FOR'] = '198.51.100.7'
        middleware.process_request(request)
        self.assertEqual(request.META['REMOTE_ADDR'], '198.51.100.7')
        for value in ('', 'https,http', 'https, https'):
            request.META['HTTP_X_FORWARDED_PROTO'] = value
            self.assertEqual(middleware.process_request(request).status_code, 400)
        request.META['HTTP_HOST'] = 'attacker.example.test'
        with self.assertRaises(DisallowedHost):
            middleware.process_request(request)

    @override_settings(ALLOWED_HOSTS=['testserver'], ZEV_PROXY_HEADERS_VERIFIED=False)
    def test_forged_https_without_provider_confirmation_fails_closed(self):
        request = RequestFactory().get('/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(ManagedHttpsMiddleware(lambda r: HttpResponse()).process_request(request).status_code, 400)

    def test_spa_callback_and_portal_routes_do_not_replace_backend_or_missing_assets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<html>React</html>', encoding='utf-8')
            validate_frontend(root)
            with self.settings(FRONTEND_ROOT=root, ROOT_URLCONF='config.native_urls'):
                for path in ('/dic/participant', '/dic/register/payment-return', '/dic/register/confirmation/order'):
                    self.assertIs(resolve(path).func, frontend)
                    response = frontend(RequestFactory().get(path))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['Cache-Control'], 'no-store')
                    response.close()
                for path in ('/api/v1/not-a-route/', '/admin/not-a-route/', '/media/private.jpg'):
                    try:
                        match = resolve(path)
                    except Resolver404:
                        continue
                    self.assertIsNot(match.func, frontend)
                with self.assertRaises(Http404):
                    frontend(RequestFactory().get('/assets/missing.js'), 'assets/missing.js')
            (root / 'api').mkdir()
            with self.assertRaises(RuntimeError):
                validate_frontend(root)

    def test_shared_worker_heartbeat_expires_and_uses_existing_cache(self):
        from .worker_health import healthy, beat
        with patch('config.worker_health.cache') as cache, patch('config.worker_health.time', return_value=1000):
            cache.get.return_value = None
            self.assertFalse(healthy())
            cache.get.return_value = 699
            self.assertFalse(healthy())
            cache.get.return_value = 990
            self.assertTrue(healthy())
            beat()
            cache.set.assert_called_once_with('dic-native-worker-heartbeat', 1000, timeout=600)

    def test_worker_http_health_requires_a_successful_processing_heartbeat(self):
        from dic.management.commands.run_dic_workers import HealthHandler
        handler = HealthHandler.__new__(HealthHandler)
        handler.path = '/health/'
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        with patch('config.worker_health.healthy', return_value=False), patch(
                'dic.management.commands.run_dic_workers.connections.close_all') as close:
            handler.do_GET()
            handler.send_response.assert_called_with(503)
            close.assert_called_once()
        with patch('config.worker_health.healthy', return_value=True), patch(
                'dic.management.commands.run_dic_workers.connections.close_all'):
            handler.do_GET()
            handler.send_response.assert_called_with(200)
