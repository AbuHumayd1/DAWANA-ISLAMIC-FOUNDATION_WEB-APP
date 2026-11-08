"""Pure renderer tests; no Django, secrets, database or network."""
import unittest
from pathlib import Path
import runpy
from unittest.mock import MagicMock, patch
from gateway import configuration


class GatewayTests(unittest.TestCase):
    def edge(self, **changes):
        return dict(PUBLIC_HOST='foundation.example.test', PORT='8080',
                    GATEWAY_TLS_MODE='trusted-edge', EDGE_TRUST_VERIFIED='1',
                    TRUSTED_EDGE_CIDRS='192.0.2.0/24', **changes)

    def test_edge_requires_explicit_trust(self):
        for changes in ({'EDGE_TRUST_VERIFIED': ''}, {'TRUSTED_EDGE_CIDRS': ''},
                        {'TRUSTED_EDGE_CIDRS': '0.0.0.0/0'}, {'TRUSTED_EDGE_CIDRS': '192.0.2.1/24'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                configuration({**self.edge(), **changes})

    def test_invalid_host_port_and_direct_key_injection_fail(self):
        for changes in ({'PUBLIC_HOST': 'evil; include /tmp/x'}, {'PORT': '80'}, {'PORT': '10000'},
                        {'PORT': '9090'}, {'PORT': '8080;'}, {'GATEWAY_TLS_MODE': 'unknown'},
                        {'GATEWAY_TLS_MODE': 'direct', 'GATEWAY_TLS_CERT_FILE': '/x;include', 'GATEWAY_TLS_KEY_FILE': '/x'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                configuration({**self.edge(), **changes})

    def test_edge_checks_peer_scheme_and_replaces_django_identity(self):
        value = configuration(self.edge())
        for expected in ('192.0.2.0/24 1;', 'if ($trusted_edge = 0)',
                         'if ($http_x_forwarded_proto != https)',
                         'proxy_set_header X-Dawana-Client-IP $http_x_real_ip;',
                         'proxy_set_header X-Forwarded-For "";'):
            self.assertIn(expected, value)

    def test_reserved_routes_private_cache_assets_and_readiness(self):
        value = configuration(self.edge())
        for expected in ('^/(api|admin)(/|$)', '^/static(/|$)', '^/(media|health)(/|$)',
                         'private, no-store', 'try_files $uri =404;',
                         'try_files $uri $uri/ /index.html;', '127.0.0.1:10000/api/v1/health/',
                         'listen 127.0.0.1:9090;', "log_format private_status '$status $request_time';"):
            self.assertIn(expected, value)

    def test_website_only_blocks_application_but_keeps_health_and_spa(self):
        value = configuration(self.edge())
        self.assertIn('return 503', value)
        self.assertIn('location = /api/v1/health/', value)
        self.assertIn('try_files $uri $uri/ /index.html;', value)
        self.assertNotIn('return 503', configuration({**self.edge(), 'DAWANA_WEBSITE_ONLY': 'false'}))

    def test_direct_tls_uses_socket_client_and_certificate_files(self):
        value = configuration({**self.edge(), 'GATEWAY_TLS_MODE': 'direct',
            'GATEWAY_TLS_CERT_FILE': '/run/tls/cert.pem', 'GATEWAY_TLS_KEY_FILE': '/run/tls/key.pem'})
        self.assertIn('listen 0.0.0.0:8080 ssl;', value)
        self.assertIn('proxy_set_header X-Dawana-Client-IP $remote_addr;', value)
        self.assertNotIn('geo $trusted_edge', value)

    def test_internal_readiness_bypasses_environment_proxy_and_requires_db_success(self):
        script = str(Path(__file__).with_name('healthcheck.py'))
        for status, body, expected in ((200, b'{"status":"ok"}', 0),
                                       (200, b'<html>SPA</html>', 1),
                                       (503, b'{"status":"unavailable"}', 1)):
            response = MagicMock()
            response.status = status
            response.read.return_value = body
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = response
            with self.subTest(status=status, body=body), \
                    patch('urllib.request.ProxyHandler') as proxy, \
                    patch('urllib.request.build_opener', return_value=opener), \
                    self.assertRaises(SystemExit) as exit_result:
                runpy.run_path(script)
            self.assertEqual(exit_result.exception.code, expected)
            proxy.assert_called_once_with({})
            opener.open.assert_called_once_with('http://127.0.0.1:9090/_container/ready', timeout=4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
