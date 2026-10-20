import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from . import tests as existing
from .models import PaymentAttempt, RegistrationOrder


@override_settings(
    MIDDLEWARE=[*settings.MIDDLEWARE, "config.staging_tester_access.DICStagingTesterMiddleware"],
    STAGING_DIC_TESTER_RESTRICTION_ENABLED=True,
    STAGING_DIC_TESTER_USERNAMES=["approved-tester"],
    PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock",
    ALLOWED_HOSTS=["testserver", "backend-staging.onrender.com"],
)
class StagingTesterAccessTests(APITestCase):
    create_pending_attempt = existing.PaymentApiTests.create_pending_attempt
    provider_result = existing.PaymentApiTests.provider_result
    initialize_url = existing.PaymentApiTests.initialize_url
    verify_url = existing.PaymentApiTests.verify_url

    def setUp(self):
        # Prepare fixtures through the real API with the gate disabled only in
        # this local test, then exercise the enabled gate with a real session.
        with override_settings(STAGING_DIC_TESTER_RESTRICTION_ENABLED=False):
            existing.PaymentApiTests.setUp(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_superuser(
            username="approved-tester", email="tester@example.test", password="test-only"
        )

    def sign_in(self):
        csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]
        response = self.client.post("/api/v1/dic/operations/auth/login/", {
            "username": "approved-tester", "password": "test-only",
        }, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        return self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]

    def test_anonymous_direct_render_mutations_are_denied_even_with_bearer(self):
        attempt = self.create_pending_attempt()
        for path in ("/api/v1/dic/orders/", self.initialize_url(),
                     self.verify_url(attempt.reference),
                     f"/api/v1/dic/orders/{self.order_id}/pricing/accept/"):
            response = self.client.post(path, {}, format="json", **self.auth,
                                        HTTP_HOST="backend-staging.onrender.com")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "staging_tester_required")
            self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_allowlist_and_operations_permission_are_both_required(self):
        self.client.force_login(self.user)
        with override_settings(STAGING_DIC_TESTER_USERNAMES=[]):
            self.assertEqual(self.client.post("/api/v1/dic/orders/", {}).status_code, 403)
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        response = self.client.post("/api/v1/dic/orders/", {})
        self.assertEqual(response.json()["code"], "staging_tester_required")

    def test_authorized_session_requires_csrf(self):
        self.sign_in()
        response = self.client.post(self.initialize_url(), {}, **self.auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staging_tester_csrf_required")

    def test_cross_origin_post_is_rejected_even_with_session_and_csrf(self):
        csrf = self.sign_in()
        response = self.client.post(self.initialize_url(), {}, **self.auth,
            HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="https://untrusted.example.test")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staging_tester_csrf_required")

    def test_logout_revokes_tester_access_even_with_valid_order_bearer(self):
        csrf = self.sign_in()
        self.assertEqual(self.client.post("/api/v1/dic/operations/auth/logout/", {},
            HTTP_X_CSRFTOKEN=csrf).status_code, 204)
        response = self.client.post(self.initialize_url(), {}, **self.auth,
                                    HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.json()["code"], "staging_tester_required")

    def test_tester_can_create_initialize_and_verify_normal_flow(self):
        csrf = self.sign_in()
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
            HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)
        order_id, token = response.data["order_id"], response.data["access_token"]
        headers = {"HTTP_X_CSRFTOKEN": csrf, "HTTP_AUTHORIZATION": f"Bearer {token}"}
        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.initialize_transaction.side_effect = lambda **kw: {
                "reference": kw["reference"],
                "authorization_url": "https://checkout.paystack.com/test-access",
            }
            init = self.client.post(self.initialize_url(order_id), {}, **headers)
            self.assertEqual(init.status_code, 200)
            ref = init.data["payment_reference"]
            factory.return_value.verify_transaction.return_value = self.provider_result(ref)
            verified = self.client.post(
                f"/api/v1/dic/orders/{order_id}/payments/{ref}/verify/", {}, **headers)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["payment_status"], "paid")

    def test_tester_session_does_not_replace_order_bearer(self):
        csrf = self.sign_in()
        self.assertEqual(self.client.post(self.initialize_url(), {},
            HTTP_X_CSRFTOKEN=csrf).status_code, 404)

    def test_draft_edition_is_still_closed_to_testers(self):
        csrf = self.sign_in()
        self.edition.registration_status = "draft"
        self.edition.save(update_fields=["registration_status"])
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
            HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 1)

    def test_bearer_confirmation_and_recovery_options_remain_available(self):
        detail = self.client.get(f"/api/v1/dic/orders/{self.order_id}/", **self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/dic/recovery/channels/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/dic/registration-options/").status_code, 200)

    def test_signed_webhook_remains_accessible_without_tester_session(self):
        attempt = self.create_pending_attempt()
        body = json.dumps({"event": "charge.success", "data": {
            "reference": attempt.reference}}).encode()
        path = "/api/v1/dic/payments/paystack/webhook/"
        invalid = self.client.post(path, body, content_type="application/json",
                                  HTTP_X_PAYSTACK_SIGNATURE="invalid")
        self.assertEqual(invalid.status_code, 400)
        signature = hmac.new(b"sk_test_unit_mock", body, hashlib.sha512).hexdigest()
        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.secret_key = "sk_test_unit_mock"
            factory.return_value.verify_transaction.return_value = self.provider_result(attempt.reference)
            response = self.client.post(path, body, content_type="application/json",
                                       HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")

    def test_disabling_gate_restores_public_bearer_flow(self):
        with override_settings(STAGING_DIC_TESTER_RESTRICTION_ENABLED=False):
            response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)

    def test_production_middleware_has_no_tester_gate(self):
        from config.settings import production

        self.assertNotIn("config.staging_tester_access.DICStagingTesterMiddleware",
                         production.MIDDLEWARE)
        with override_settings(MIDDLEWARE=production.MIDDLEWARE):
            response = APIClient().post("/api/v1/dic/orders/", self.order_payload, format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)
