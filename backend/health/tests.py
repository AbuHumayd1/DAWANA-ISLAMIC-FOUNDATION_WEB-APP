from rest_framework.test import APITestCase
from django.test import override_settings


class HealthCheckTests(APITestCase):
    def test_health_endpoint_is_public_and_reports_healthy(self):
        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CORS_URLS_REGEX=r"^/api/.*$",
    )
    def test_frontend_origin_is_allowed_without_credentials(self):
        response = self.client.get(
            "/api/v1/health/",
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertNotIn("Access-Control-Allow-Credentials", response)

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
