from unittest.mock import patch
from django.db import OperationalError
from rest_framework.test import APITestCase
from django.test import override_settings


class HealthCheckTests(APITestCase):
    def test_health_endpoint_is_public_and_reports_healthy(self):
        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_database_failure_is_generic_and_not_cached(self):
        with patch('health.views.connection.cursor', side_effect=OperationalError('private connection detail')):
            response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('private', response.content.decode())

    @override_settings(DIC_BACKGROUND_WORKER_ENABLED=True, DIC_WORKER_HEARTBEAT_CACHE=True)
    def test_native_readiness_requires_the_independent_durable_worker(self):
        with patch('config.worker_health.healthy', return_value=False):
            self.assertEqual(self.client.get('/api/v1/health/').status_code, 503)
        with patch('config.worker_health.healthy', return_value=True), patch('dic.recovery.channel_available', return_value=True):
            self.assertEqual(self.client.get('/api/v1/health/').status_code, 200)

    @override_settings(DIC_BACKGROUND_WORKER_ENABLED=True, DIC_WORKER_HEARTBEAT_CACHE=True,
                       DIC_RECOVERY_ENCRYPTION_KEY='', DEFAULT_FROM_EMAIL='', RESEND_API_KEY='')
    def test_web_health_is_independent_while_full_readiness_refuses_missing_delivery(self):
        with patch('config.worker_health.healthy', return_value=True):
            self.assertEqual(self.client.get('/api/v1/health/web/').status_code, 200)
            self.assertEqual(self.client.get('/api/v1/health/').status_code, 503)
        with patch('health.views.connection.cursor', side_effect=OperationalError('private connection detail')):
            response = self.client.get('/api/v1/health/web/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CORS_URLS_REGEX=r"^/api/.*$",
    )
    def test_frontend_origin_supports_shared_session_credentials(self):
        response = self.client.get(
            "/api/v1/health/",
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CORS_URLS_REGEX=r"^/api/.*$",
    )
    def test_unconfigured_frontend_origin_is_not_allowed(self):
        response = self.client.get(
            "/api/v1/health/",
            HTTP_ORIGIN="https://untrusted.example",
        )

        self.assertNotIn("Access-Control-Allow-Origin", response)

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CORS_URLS_REGEX=r"^/api/.*$",
    )
    def test_frontend_preflight_allows_order_idempotency_and_bearer_headers(self):
        response = self.client.options(
            "/api/v1/dic/orders/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type, idempotency-key",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertIn("idempotency-key", response["Access-Control-Allow-Headers"])
