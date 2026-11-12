"""Database-free regressions through the real CSRF/CORS middleware and views."""
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, override_settings

from .site_context import public_site


@override_settings(
    ROOT_URLCONF='config.urls', DEBUG=False,
    ALLOWED_HOSTS=['api.dawanaislamicfoundation.org'],
    FRONTEND_ORIGIN='https://dawanaislamicfoundation.org',
    CORS_ALLOWED_ORIGINS=['https://dawanaislamicfoundation.org'],
    CSRF_TRUSTED_ORIGINS=['https://dawanaislamicfoundation.org'],
    CORS_ALLOW_CREDENTIALS=True, CORS_ALLOW_ALL_ORIGINS=False,
    CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_URLS_REGEX=r'^/api/',
    SECURE_SSL_REDIRECT=True, CSRF_COOKIE_SECURE=True,
    CSRF_COOKIE_DOMAIN=None, CSRF_COOKIE_SAMESITE='Lax',
    MIDDLEWARE=[
        'django.middleware.security.SecurityMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ],
)
class OperationsSecurityTests(SimpleTestCase):
    csrf_url = '/api/v1/dic/operations/auth/csrf/'
    login_url = '/api/v1/dic/operations/auth/login/'

    def browser(self):
        return Client(enforce_csrf_checks=True, HTTP_HOST='api.dawanaislamicfoundation.org',
                      HTTP_ORIGIN='https://dawanaislamicfoundation.org')

    def post(self, browser, token=None, **headers):
        if token is not None:
            headers['HTTP_X_CSRFTOKEN'] = token
        return browser.post(self.login_url, {'username': 'synthetic', 'password': 'unused'},
                            content_type='application/json', secure=True, **headers)

    def test_csrf_bootstrap_delivers_secure_host_only_cookie_and_credentialed_cors(self):
        response = self.browser().get(self.csrf_url, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['csrfToken'])
        cookie = response.cookies['csrftoken']
        self.assertTrue(cookie['secure'])
        self.assertEqual(cookie['domain'], '')
        self.assertEqual(cookie['path'], '/')
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(response['Access-Control-Allow-Origin'], 'https://dawanaislamicfoundation.org')
        self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('Cookie', response['Vary'])

    def test_trusted_cross_origin_cookie_and_token_reach_authentication(self):
        browser = self.browser()
        token = browser.get(self.csrf_url, secure=True).json()['csrfToken']
        with patch('dic.operations_api.authenticate', return_value=None) as authenticate, \
                patch('rest_framework.throttling.ScopedRateThrottle.allow_request', return_value=True):
            response = self.post(browser, token)
        self.assertEqual(response.status_code, 401)
        authenticate.assert_called_once()

    def test_json_token_alone_cannot_replace_missing_cookie(self):
        browser = self.browser()
        token = browser.get(self.csrf_url, secure=True).json()['csrfToken']
        browser.cookies.clear()
        with patch('dic.operations_api.authenticate') as authenticate:
            self.assertEqual(self.post(browser, token).status_code, 403)
        authenticate.assert_not_called()

    def test_missing_mismatched_token_and_untrusted_origin_fail_before_authentication(self):
        browser = self.browser()
        token = browser.get(self.csrf_url, secure=True).json()['csrfToken']
        for value, headers in (
            (None, {}), ('A' * 64, {}),
            (token, {'HTTP_ORIGIN': 'https://attacker.example'}),
            (token, {'HTTP_ORIGIN': 'https://dawanaislamicfoundation.org.attacker.example'}),
        ):
            with self.subTest(headers=headers, missing=value is None), \
                    patch('dic.operations_api.authenticate') as authenticate:
                response = self.post(browser, value, **headers)
                self.assertEqual(response.status_code, 403)
                authenticate.assert_not_called()
                if headers:
                    self.assertNotIn('Access-Control-Allow-Origin', response)

    def test_preflight_allows_only_exact_frontend_and_required_headers(self):
        for origin, allowed in (('https://dawanaislamicfoundation.org', True),
                                ('https://attacker.example', False)):
            response = self.browser().options(self.login_url, secure=True, HTTP_ORIGIN=origin,
                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,x-csrftoken')
            self.assertEqual('Access-Control-Allow-Origin' in response, allowed)
            if allowed:
                self.assertIn('x-csrftoken', response['Access-Control-Allow-Headers'])

    def test_admin_operations_link_uses_validated_public_origin_and_permission(self):
        for permitted in (True, False):
            context = {**public_site(None), 'is_popup': False, 'has_permission': True,
                       'perms': SimpleNamespace(dic=SimpleNamespace(can_view_dic_operations=permitted))}
            html = render_to_string('admin/base_site.html', context)
            link = 'href="https://dawanaislamicfoundation.org/dic/operations">Operations Portal</a>'
            self.assertEqual(link in html, permitted)
            self.assertNotIn('href="/dic/operations"', html)
