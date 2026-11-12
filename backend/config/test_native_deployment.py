from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
from io import BytesIO
from django.test import SimpleTestCase, TestCase, Client, RequestFactory, override_settings
from django.http import HttpResponse, Http404
from django.core.exceptions import DisallowedHost
from django.urls import resolve, Resolver404
from .native_defaults import configure
from .native_security import ManagedHttpsMiddleware
from .spa import frontend, validate_frontend, static_headers


class NativeDeploymentTests(SimpleTestCase):
    def test_real_native_wsgi_starts_without_an_automation_actor_or_database_access(self):
        import os
        import subprocess
        import sys
        import textwrap

        backend = Path(__file__).resolve().parents[1]
        code = 'import sys; sys.path.insert(0, ' + repr(str(backend)) + ')\n' + textwrap.dedent('''
            import os
            from unittest.mock import patch
            import environ
            from django.db.backends.base.base import BaseDatabaseWrapper
            def denied(*args, **kwargs):
                raise RuntimeError('External access is forbidden in this startup regression.')
            with patch.object(environ.Env, 'read_env'), \\
                    patch.object(BaseDatabaseWrapper, 'ensure_connection', denied), \\
                    patch('socket.socket.connect', denied), \\
                    patch('socket.create_connection', denied):
                from django.core.wsgi import get_wsgi_application
                application = get_wsgi_application()
                from django.conf import settings
                assert callable(application)
                assert 'DIC_AUTOMATION_ACTOR_ID' not in os.environ
                assert settings.DIC_AUTOMATION_ACTOR_ID == 0
                assert settings.DEBUG is False
                assert settings.SECURE_SSL_REDIRECT is True
                assert settings.SESSION_COOKIE_SECURE is True
                assert settings.DATABASES['default']['OPTIONS']['sslmode'] == 'verify-full'
                assert settings.PAYSTACK_LIVE_ENABLED is False
            print('PASS: native WSGI starts without an actor; production security retained.')
        ''')
        environment = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        environment.update(
            DJANGO_SETTINGS_MODULE='config.settings.zevcloud',
            PUBLIC_HOST='backend.example.test', FRONTEND_ORIGIN='https://foundation.example.test',
            DJANGO_SECRET_KEY='synthetic-startup-regression-only-' * 3,
            DATABASE_URL='postgresql://synthetic:unused@database.example.test/startup_only')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], env=environment,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: native WSGI starts without an actor', result.stdout)

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

    def test_defaults_use_frontend_for_callbacks_and_bound_cross_origin_access(self):
        env = configure({'PUBLIC_HOST': 'api.foundation.example.test', 'FRONTEND_ORIGIN': 'https://foundation.example.test',
                         'DJANGO_CORS_ALLOWED_ORIGINS': 'https://old.example.test'})
        self.assertEqual(env['PAYSTACK_CALLBACK_URL'], 'https://foundation.example.test/dic/register/payment-return')
        self.assertEqual(env['DIC_PORTAL_EMAIL_VERIFY_URL'], 'https://foundation.example.test/dic/participant')
        self.assertEqual(env['DAWANA_WEBSITE_ONLY'], 'false')
        self.assertEqual(env['PAYSTACK_LIVE_ENABLED'], 'false')
        self.assertEqual(env['DJANGO_CORS_ALLOWED_ORIGINS'], 'https://foundation.example.test')
        self.assertEqual(env['DJANGO_CSRF_TRUSTED_ORIGINS'], 'https://foundation.example.test')
        self.assertEqual(env['DJANGO_ALLOWED_HOSTS'], 'api.foundation.example.test')
        self.assertEqual(env['DJANGO_DEBUG'], 'false')
        self.assertNotIn('ZEV_PROXY_HEADERS_VERIFIED', env)
        self.assertNotIn('TRUSTED_EDGE_CIDRS', env)
        for credential in ('DIC_AUTOMATION_ACTOR_ID', 'DIC_RECOVERY_ENCRYPTION_KEY', 'DEFAULT_FROM_EMAIL', 'RESEND_API_KEY'):
            self.assertNotIn(credential, env)

    @override_settings(DIC_RECOVERY_ENCRYPTION_KEY='', DEFAULT_FROM_EMAIL='', RESEND_API_KEY='',
                       DIC_RECOVERY_DELIVERY_WORKER_ENABLED=True, DIC_EMAIL_RECOVERY_ENABLED=True)
    def test_missing_operation_credentials_cannot_issue_or_encrypt_recovery_or_portal_codes(self):
        from types import SimpleNamespace
        from dic.recovery import channel_available, encrypt_delivery_payload, RecoveryDeliveryError
        from dic.recovery_views import RecoveryChallengeView, RecoveryChannelUnavailable
        from dic.participant_api import PortalChallengeView
        self.assertFalse(channel_available('email'))
        with self.assertRaises(RecoveryDeliveryError):
            encrypt_delivery_payload('email', 'owned@example.test', '123456')
        request = SimpleNamespace(data={'channel': 'email', 'contact': 'owned@example.test'})
        for view in (RecoveryChallengeView, PortalChallengeView):
            with self.assertRaises(RecoveryChannelUnavailable) as error:
                view().post(request)
            self.assertEqual(error.exception.status_code, 503)

    def test_frontend_origin_rejects_credentials_http_paths_and_wildcards(self):
        for origin in ('', 'http://foundation.example.test', 'https://user@foundation.example.test',
                       'https://foundation.example.test/', 'https://*.example.test',
                       'https://foundation.example.test?token=secret'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                configure({'PUBLIC_HOST': 'api.foundation.example.test', 'FRONTEND_ORIGIN': origin})

    @override_settings(ALLOWED_HOSTS=['foundation.example.test'])
    def test_scheme_is_exact_and_unverified_identity_headers_are_ignored(self):
        middleware = ManagedHttpsMiddleware(lambda request: HttpResponse())
        request = RequestFactory().get('/', HTTP_HOST='foundation.example.test',
            HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_FOR='spoof', HTTP_X_REAL_IP='spoof')
        self.assertIsNone(middleware.process_request(request))
        self.assertNotIn('HTTP_X_FORWARDED_FOR', request.META)
        self.assertNotIn('HTTP_X_REAL_IP', request.META)
        request.META['HTTP_X_FORWARDED_FOR'] = '198.51.100.7'
        middleware.process_request(request)
        self.assertEqual(request.META['REMOTE_ADDR'], '127.0.0.1')
        for value in ('', 'https,http', 'https, https'):
            request.META['HTTP_X_FORWARDED_PROTO'] = value
            self.assertEqual(middleware.process_request(request).status_code, 400)
        request.META['HTTP_HOST'] = 'attacker.example.test'
        with self.assertRaises(DisallowedHost):
            middleware.process_request(request)

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_missing_scheme_fails_closed_without_an_acknowledgement_flag(self):
        request = RequestFactory().get('/')
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


@override_settings(
    ROOT_URLCONF='config.urls', DEBUG=False,
    ALLOWED_HOSTS=['api.foundation.example.test'],
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
    SESSION_COOKIE_DOMAIN=None, CSRF_COOKIE_DOMAIN=None,
    SESSION_COOKIE_SAMESITE='Lax', CSRF_COOKIE_SAMESITE='Lax',
    CORS_ALLOWED_ORIGINS=['https://foundation.example.test'],
    CSRF_TRUSTED_ORIGINS=['https://foundation.example.test'],
    CORS_ALLOW_CREDENTIALS=True, CORS_ALLOW_ALL_ORIGINS=False,
    CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_URLS_REGEX=r'^/api/',
    MIDDLEWARE=[
        'config.native_security.ManagedHttpsMiddleware',
        'django.middleware.security.SecurityMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
    ],
)
class NativeAuthenticationTests(TestCase):
    """Real session/CSRF integration on disposable CI PostgreSQL only.

    Browser SameSite acceptance still requires the documented sibling domains.
    """
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        user = get_user_model().objects.create_user(
            username='native-operator', password='synthetic-native-password', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='can_view_dic_operations'))
        self.browser = Client(enforce_csrf_checks=True, HTTP_HOST='api.foundation.example.test',
                              HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://foundation.example.test')

    def test_session_login_rotation_me_logout_and_host_only_secure_cookies(self):
        csrf = self.browser.get('/api/v1/dic/operations/auth/csrf/')
        self.assertEqual(csrf['Access-Control-Allow-Origin'], 'https://foundation.example.test')
        self.assertEqual(csrf['Access-Control-Allow-Credentials'], 'true')
        self.assertTrue(csrf.cookies['csrftoken']['secure'])
        self.assertEqual(csrf.cookies['csrftoken']['domain'], '')
        login = self.browser.post('/api/v1/dic/operations/auth/login/',
            {'username': 'native-operator', 'password': 'synthetic-native-password'},
            content_type='application/json', HTTP_X_CSRFTOKEN=csrf.json()['csrfToken'])
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.cookies['sessionid']['secure'])
        self.assertTrue(login.cookies['sessionid']['httponly'])
        self.assertEqual(login.cookies['sessionid']['samesite'], 'Lax')
        self.assertEqual(login.cookies['sessionid']['domain'], '')
        self.assertNotEqual(login.cookies['csrftoken'].value, csrf.cookies['csrftoken'].value)
        stale = self.browser.post('/api/v1/dic/operations/auth/logout/', {},
            content_type='application/json', HTTP_X_CSRFTOKEN=csrf.json()['csrfToken'])
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(self.browser.get('/api/v1/dic/operations/auth/me/').status_code, 200)
        token = self.browser.get('/api/v1/dic/operations/auth/csrf/').json()['csrfToken']
        self.assertEqual(self.browser.post('/api/v1/dic/operations/auth/logout/', {},
            content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 204)
        self.assertIn(self.browser.get('/api/v1/dic/operations/auth/me/').status_code, (401, 403))

    def test_json_csrf_token_without_cookie_cannot_log_in(self):
        token = self.browser.get('/api/v1/dic/operations/auth/csrf/').json()['csrfToken']
        self.browser.cookies.clear()
        response = self.browser.post('/api/v1/dic/operations/auth/login/',
            {'username': 'native-operator', 'password': 'synthetic-native-password'},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('sessionid', response.cookies)

    def test_valid_csrf_does_not_grant_operations_permission(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user(
            username='staff-without-operations', password='synthetic-native-password', is_staff=True)
        token = self.browser.get('/api/v1/dic/operations/auth/csrf/').json()['csrfToken']
        response = self.browser.post('/api/v1/dic/operations/auth/login/',
            {'username': 'staff-without-operations', 'password': 'synthetic-native-password'},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('sessionid', response.cookies)

    def test_csrf_and_cors_refuse_foreign_origin_and_missing_token(self):
        endpoint = '/api/v1/dic/operations/auth/login/'
        token = self.browser.get('/api/v1/dic/operations/auth/csrf/').json()['csrfToken']
        self.assertEqual(self.browser.post(endpoint, {}, content_type='application/json').status_code, 403)
        foreign = self.browser.post(endpoint, {}, content_type='application/json',
            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://attacker.example.test')
        self.assertEqual(foreign.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', foreign)
        allowed = self.browser.options(endpoint, HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,x-csrftoken')
        self.assertEqual(allowed['Access-Control-Allow-Origin'], 'https://foundation.example.test')
        foreign = self.browser.options(endpoint, HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ORIGIN='https://attacker.example.test')
        self.assertNotIn('Access-Control-Allow-Origin', foreign)

    def test_portal_csrf_json_and_cookie_scope_remain_compatible(self):
        from dic.participant_api import cookie, COOKIE, COOKIE_PATH
        response = self.browser.get('/api/v1/dic/participant/auth/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['csrfToken'])
        self.assertEqual(response['Access-Control-Allow-Origin'], 'https://foundation.example.test')
        cookie(response, COOKIE, 'synthetic-test-token', 60)
        self.assertEqual(response.cookies[COOKIE]['path'], COOKIE_PATH)
        self.assertEqual(response.cookies[COOKIE]['samesite'], 'Lax')
        self.assertTrue(response.cookies[COOKIE]['secure'])
        self.assertTrue(response.cookies[COOKIE]['httponly'])

    def test_http_redirect_and_backend_does_not_serve_spa(self):
        self.assertEqual(self.browser.get('/api/v1/health/', HTTP_X_FORWARDED_PROTO='http').status_code, 301)
        self.assertEqual(self.browser.get('/dic/register/payment-return').status_code, 404)
