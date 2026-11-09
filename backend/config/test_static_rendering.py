"""Real manifest collection and API rendering without external dependencies."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class StaticRenderingTests(SimpleTestCase):
    def run_settings_process(self, module, directory, code):
        backend = Path(__file__).resolve().parents[1]
        environment = {key: os.environ[key] for key in
            ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
        # No connection is made; this is only a settings fixture for Render's
        # CA-path check, never a trusted certificate used by a TLS client.
        ca = Path(directory) / 'synthetic-unused-ca.pem'
        ca.write_text('Unused settings fixture.', encoding='ascii')
        environment.update(
            DJANGO_SETTINGS_MODULE=module,
            DJANGO_SECRET_KEY='synthetic-static-rendering-regression-only-' * 3,
            DATABASE_URL='postgresql://synthetic:unused@database.example.test/static_test',
            DB_SSLROOTCERT=str(ca), DAWANA_WEBSITE_ONLY='false',
            DJANGO_ALLOWED_HOSTS='backend.example.test',
            PUBLIC_HOST='backend.example.test', FRONTEND_ORIGIN='https://portal.example.test')
        prelude = 'import sys; sys.path.insert(0, ' + repr(str(backend)) + ')\n'
        prelude += 'static_root = ' + repr(str(Path(directory) / 'static')) + '\n'
        return subprocess.run([sys.executable, '-I', '-B', '-c', prelude + textwrap.dedent(code)],
            env=environment, capture_output=True, text=True, timeout=120)

    def test_offline_build_manifest_contains_browsable_api_and_admin_assets(self):
        with TemporaryDirectory() as directory:
            result = self.run_settings_process('config.settings.build', directory, '''
                import re
                from pathlib import Path
                from importlib.util import find_spec
                from unittest.mock import patch
                from django.conf import settings
                import django
                def denied(*args, **kwargs):
                    raise AssertionError('Build must not access the network or database.')
                with patch('socket.socket.connect', denied), \\
                        patch('socket.create_connection', denied), \\
                        patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', denied):
                    settings.STATIC_ROOT = static_root
                    django.setup()
                    assert settings.DATABASES == {}
                    from django.core.management import call_command
                    call_command('collectstatic', interactive=False, verbosity=0)
                    from django.contrib.staticfiles.storage import staticfiles_storage
                    assert staticfiles_storage.manifest_strict
                    template = (Path(find_spec('rest_framework').origin).parent /
                        'templates/rest_framework/base.html').read_text(encoding='utf-8')
                    # Check every literal static reference in the actual DRF template.
                    assets = re.findall(r"{%\\s*static\\s+[\\\"']([^\\\"']+)[\\\"']", template)
                    assert 'rest_framework/css/bootstrap.min.css' in assets
                    for asset in assets + ['admin/css/base.css']:
                        url = staticfiles_storage.url(asset)
                        assert url.startswith('/static/')
                        assert staticfiles_storage.stored_name(asset) != asset
                    try:
                        staticfiles_storage.url('deliberately-missing-regression.css')
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Manifest validation must remain strict.')
                print('PASS: offline manifest includes DRF and Admin assets; validation stays strict.')
            ''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: offline manifest', result.stdout)

    def test_production_and_render_api_responses_do_not_render_static_templates(self):
        for module in ('config.settings.production', 'config.settings.render'):
            with self.subTest(module=module), TemporaryDirectory() as directory:
                result = self.run_settings_process(module, directory, '''
                    import json
                    from pathlib import Path
                    from unittest.mock import patch
                    import environ
                    import django
                    from django.conf import settings
                    def denied(*args, **kwargs):
                        raise AssertionError('Unexpected external access.')
                    with patch.object(environ.Env, 'read_env'), \\
                            patch('socket.socket.connect', denied), \\
                            patch('socket.create_connection', denied), \\
                            patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', denied):
                        settings.STATIC_ROOT = static_root
                        Path(static_root).mkdir()
                        (Path(static_root) / 'staticfiles.json').write_text(json.dumps(
                            {'version': '1.1', 'hash': '', 'paths': {}}), encoding='utf-8')
                        django.setup()
                        assert settings.DEBUG is False
                        assert settings.REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] == [
                            'rest_framework.renderers.JSONRenderer']
                        from django.contrib.staticfiles.storage import staticfiles_storage
                        assert staticfiles_storage.manifest_strict
                        try:
                            staticfiles_storage.url('rest_framework/css/bootstrap.min.css')
                        except ValueError:
                            pass
                        else:
                            raise AssertionError('Fixture must reproduce the missing manifest entry.')
                        from django.db import OperationalError
                        from django.test import Client, override_settings
                        from rest_framework.exceptions import APIException, NotFound, PermissionDenied
                        from rest_framework.test import APIRequestFactory
                        from rest_framework.views import APIView
                        class ErrorView(APIView):
                            authentication_classes = []
                            permission_classes = []
                            error = None
                            def get(self, request):
                                raise self.error()
                        class Unavailable(APIException):
                            status_code = 503
                        browser = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                        client = Client(HTTP_HOST='backend.example.test', HTTP_X_FORWARDED_PROTO='https')
                        # An empty strict manifest must not break health or error rendering.
                        with patch('health.views.connection') as database, \\
                                override_settings(HEALTH_CHECK_WORKERS=False), \\
                                patch.object(staticfiles_storage, 'url', side_effect=AssertionError(
                                    'API rendering must not resolve static URLs.')) as static_url:
                            for accept in ('application/json', '*/*', browser):
                                for path in ('/api/v1/health/', '/api/v1/health/web/'):
                                    response = client.get(path, secure=True, HTTP_ACCEPT=accept)
                                    assert response.status_code == 200
                                    assert response['Content-Type'] == 'application/json'
                                    assert response.json() == {'status': 'ok'}
                                database.cursor.side_effect = OperationalError('private-db-detail')
                                response = client.get('/api/v1/health/', secure=True, HTTP_ACCEPT=accept)
                                assert response.status_code == 503
                                assert response.json() == {'status': 'unavailable'}
                                database.cursor.side_effect = None
                                for exception, status in ((PermissionDenied, 403), (NotFound, 404),
                                        (Unavailable, 503)):
                                    response = ErrorView.as_view(error=exception)(
                                        APIRequestFactory().get('/api/error/', HTTP_ACCEPT=accept))
                                    response.render()
                                    assert response.status_code == status
                                    assert response['Content-Type'] == 'application/json'
                            response = client.get('/api/v1/health/web/', secure=True, HTTP_ACCEPT='text/html')
                            assert response.status_code == 406
                            assert response['Content-Type'] == 'application/json'
                            static_url.assert_not_called()
                    print('PASS: production API and health responses preserve JSON statuses without static rendering.')
                ''')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('PASS: production API', result.stdout)
