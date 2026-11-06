import os
import runpy
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from config.deployment_security import validate_database_tls


class RenderConfigurationTests(SimpleTestCase):
    def test_render_port_and_optional_self_managed_bind(self):
        path = Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'
        with patch.dict(os.environ, {'DJANGO_DEPLOYMENT_TARGET': 'render', 'PORT': '12345'}):
            self.assertEqual(runpy.run_path(str(path))['bind'], '0.0.0.0:12345')
        with patch.dict(os.environ, {'DJANGO_DEPLOYMENT_TARGET': 'self-managed', 'PORT': '12345'}):
            config = runpy.run_path(str(path))
            self.assertEqual(config['bind'], '127.0.0.1:10000')
            self.assertEqual(config['forwarded_allow_ips'], '127.0.0.1')
        with patch.dict(os.environ, {'DJANGO_DEPLOYMENT_TARGET': 'render', 'PORT': '0'}):
            with self.assertRaises(ValueError): runpy.run_path(str(path))

    def test_authenticated_tls_default_and_explicit_mode(self):
        for target in ('render', 'self-managed'):
            validate_database_tls(target, 'database.example.test')
            validate_database_tls(target, 'database.example.test', 'verify-full')

    def test_no_host_can_qualify_for_weaker_tls(self):
        for target in ('render', 'self-managed'):
            for host in ('arbitrary.invalid', 'approved-internal', 'dpg-example.render.com'):
                for mode in (None, '', 'require', 'verify-ca', 'prefer', 'disable', 'VERIFY-FULL'):
                    with self.subTest(target=target, host=host, mode=mode), self.assertRaises(ImproperlyConfigured):
                        validate_database_tls(target, host, mode)

    def test_missing_host_and_invalid_target_are_rejected(self):
        for target, host in [('render', ''), ('render', None), ('render', '/var/run/postgresql'),
                ('render', 'first,second'), ('unsupported', 'database.example.test')]:
            with self.assertRaises(ImproperlyConfigured): validate_database_tls(target, host)

    def test_staging_inherits_and_revalidates_without_overriding_tls(self):
        import ast
        root = Path(__file__).resolve().parents[1] / 'config/settings'
        tree = ast.parse((root / 'staging.py').read_text(encoding='utf-8'))
        assignments = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AugAssign))]
        self.assertFalse(any('sslmode' in ast.unparse(node) for node in assignments))
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'validate_database_tls' for node in ast.walk(tree)))
        self.assertIn("env('DB_SSLMODE', default='verify-full')", (root / 'production.py').read_text(encoding='utf-8'))

    def test_final_release_validation_rejects_overlay_downgrade(self):
        from config.release_security import validate_production
        from .test_release_readiness import ReleaseReadinessTests
        config = ReleaseReadinessTests().config()
        config['DATABASES']['default']['OPTIONS']['sslmode'] = 'require'
        with self.assertRaises(ImproperlyConfigured): validate_production(config)
