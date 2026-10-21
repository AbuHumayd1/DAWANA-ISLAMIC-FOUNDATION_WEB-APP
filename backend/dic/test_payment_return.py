import hashlib
import hmac
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from unittest import TextTestResult

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from . import tests as fixtures
from .models import PaymentAttempt, PaymentReturnGrant, RegistrationOrder


@override_settings(PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock", PAYSTACK_HTTP_TIMEOUT_SECONDS=10)
class PaymentReturnTests(APITestCase):
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def setUp(self):
        fixtures.PaymentApiTests.setUp(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]

    def prepare(self, order_id=None, token=None, client=None, csrf=None):
        return (client or self.client).post(
            reverse("dic:payment-return-grant", args=[order_id or self.order_id]), {}, format="json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.access_token}", HTTP_X_CSRFTOKEN=csrf or self.csrf,
        )

    def status(self, payload=None, client=None, csrf=None):
        return (client or self.client).post(reverse("dic:payment-return-status"), payload or {}, format="json", HTTP_X_CSRFTOKEN=csrf or self.csrf)

    @patch("dic.payment_return.PaystackClient")
    def test_verified_success_survives_duplicate_callbacks_and_reload_without_bearer_or_draft(self, factory):
        attempt = self.create_pending_attempt()
        self.assertEqual(self.prepare().status_code, 200)
        factory.return_value.verify_transaction.return_value = self.provider_result(attempt.reference)
        response = self.status({"reference": attempt.reference})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["order"]["payment_status"], "paid")
        self.assertEqual(response.data["order"]["order_id"], str(self.order_id))
        self.assertEqual(len(response.data["order"]["participants"]), 1)
        fresh_tab = APIClient(enforce_csrf_checks=True)
        fresh_tab.cookies = self.client.cookies.copy()
        for payload in ({"reference": attempt.reference}, {"order_id": str(self.order_id)}):
            reloaded = self.status(payload, client=fresh_tab)
            self.assertEqual(reloaded.data["order"]["payment_status"], "paid")
            self.assertNotIn("access_token", reloaded.data)
            self.assertNotIn(self.access_token, json.dumps(reloaded.data))
            self.assertIn("no-store", reloaded["Cache-Control"])
        factory.return_value.verify_transaction.assert_called_once()
        factory.return_value.initialize_transaction.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    @patch("dic.payment_return.PaystackClient")
    def test_pending_failed_and_verification_outage_never_initialize(self, factory):
        from .payments import PaystackTransportError
        attempt = self.create_pending_attempt()
        self.prepare()
        for provider_status, expected in (("pending", "pending"), ("failed", "failed")):
            factory.return_value.verify_transaction.return_value = self.provider_result(attempt.reference, status=provider_status)
            result = self.status({"reference": attempt.reference})
            self.assertEqual(result.status_code, 200)
            self.assertNotEqual(result.data["order"]["payment_status"], "paid")
            self.assertEqual(result.data["order"]["attempt_status"], expected)
        factory.return_value.verify_transaction.side_effect = PaystackTransportError("synthetic")
        self.assertTrue(self.status({"reference": attempt.reference}).data["order"]["verification_unavailable"])
        factory.return_value.initialize_transaction.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    @patch("dic.payment_return.PaystackClient")
    def test_missing_expired_revoked_and_rotated_authority_is_denied(self, factory):
        attempt = self.create_pending_attempt()
        self.assertEqual(self.status({"reference": attempt.reference}).status_code, 404)
        self.prepare()
        grant = PaymentReturnGrant.objects.get()
        for field, value in (("expires_at", timezone.now() - timedelta(seconds=1)), ("revoked_at", timezone.now())):
            PaymentReturnGrant.objects.filter(pk=grant.pk).update(**{field: value})
            self.assertEqual(self.status({"reference": attempt.reference}).status_code, 404)
            PaymentReturnGrant.objects.filter(pk=grant.pk).update(expires_at=timezone.now() + timedelta(hours=1), revoked_at=None)
        RegistrationOrder.objects.filter(pk=self.order.pk).update(access_token_revoked_at=timezone.now())
        self.assertEqual(self.status({"reference": attempt.reference}).status_code, 404)
        RegistrationOrder.objects.filter(pk=self.order.pk).update(access_token_revoked_at=None, access_token_digest="rotated")
        self.assertEqual(self.status({"reference": attempt.reference}).status_code, 404)
        factory.assert_not_called()

    def test_expired_server_session_cannot_be_replayed(self):
        self.prepare()
        Session.objects.filter(session_key=self.client.cookies[settings.SESSION_COOKIE_NAME].value).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.status({"order_id": str(self.order_id)}).status_code, 404)

    @patch("dic.payment_return.PaystackClient")
    def test_multiple_orders_foreign_references_and_forged_hints(self, factory):
        attempt = self.create_pending_attempt()
        self.prepare()
        created = self.client.post(reverse("dic:order-create"), self.order_payload, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        second = RegistrationOrder.objects.get(public_id=created.data["order_id"])
        foreign = PaymentAttempt.objects.create(order=second, reference="DIC-foreign", amount_kobo=100, currency="NGN")
        self.assertEqual(self.status({"reference": foreign.reference}).status_code, 404)
        self.assertEqual(self.status({"reference": "DIC-forged"}).status_code, 404)
        self.assertEqual(self.status({"order_id": str(second.public_id), "reference": attempt.reference}).status_code, 404)
        self.assertEqual(self.prepare(second.public_id, created.data["access_token"]).status_code, 200)
        listed = self.status()
        self.assertEqual(len(listed.data["orders"]), 2)
        self.assertEqual(PaymentReturnGrant.objects.count(), 2)
        factory.assert_not_called()

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_csrf_bearer_and_cookie_security(self):
        url = reverse("dic:payment-return-grant", args=[self.order_id])
        self.assertEqual(self.client.post(url, {}, format="json", **self.auth).status_code, 403)
        self.assertEqual(self.client.post(url, {}, format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 404)
        response = self.prepare()
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(self.client.post(reverse("dic:payment-return-status"), {}, format="json").status_code, 403)
        self.assertEqual(self.client.post(reverse("dic:payment-return-status"), {}, format="json", HTTP_X_CSRFTOKEN=self.csrf, HTTP_ORIGIN="https://evil.example").status_code, 403)

    def test_tester_gate_does_not_replace_order_authorization(self):
        middleware = [*settings.MIDDLEWARE, "config.staging_tester_access.DICStagingTesterMiddleware"]
        with override_settings(MIDDLEWARE=middleware, STAGING_DIC_TESTER_RESTRICTION_ENABLED=True, STAGING_DIC_TESTER_USERNAMES=["ordinary-return-tester"]):
            self.client = APIClient(enforce_csrf_checks=True)
            self.csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]
            self.assertEqual(self.prepare().status_code, 403)
            self.assertEqual(self.status().status_code, 403)
            user = get_user_model().objects.create_user(username="ordinary-return-tester", password="synthetic-test-only")
            user.groups.add(Group.objects.create(name="DIC Staging Testers"))
            self.client.force_login(user)
            self.csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]
            self.assertEqual(self.status({"order_id": str(self.order_id)}).status_code, 404)
            self.assertEqual(self.prepare().status_code, 200)
            user.is_active = False
            user.save(update_fields=["is_active"])
            self.assertEqual(self.status().status_code, 403)


@override_settings(PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock", PAYSTACK_HTTP_TIMEOUT_SECONDS=10)
class PaymentReturnConcurrencyTests(TransactionTestCase):
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result
    prepare = PaymentReturnTests.prepare

    def setUp(self):
        self.client = APIClient()
        fixtures.PaymentApiTests.setUp(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]

    def test_webhook_and_duplicate_callback_settle_one_existing_attempt_concurrently(self):
        attempt = self.create_pending_attempt()
        self.prepare()
        provider_data = self.provider_result(attempt.reference)
        barrier = threading.Barrier(3)
        def verify(reference):
            barrier.wait(timeout=15)
            return provider_data
        body = json.dumps({"event": "charge.success", "data": {"reference": attempt.reference}}).encode()
        signature = hmac.new(b"sk_test_unit_mock", body, hashlib.sha512).hexdigest()
        def request(webhook):
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                client.cookies = self.client.cookies.copy()
                if webhook:
                    return client.post(reverse("dic:paystack-webhook"), body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature).status_code
                return client.post(reverse("dic:payment-return-status"), {"reference": attempt.reference}, format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code
            finally:
                close_old_connections()
        with patch("dic.payment_return.PaystackClient") as callback, patch("dic.payment_views.PaystackClient") as webhook:
            webhook.return_value.secret_key = "sk_test_unit_mock"
            callback.return_value.verify_transaction.side_effect = verify
            webhook.return_value.verify_transaction.side_effect = verify
            with ThreadPoolExecutor(max_workers=3) as pool:
                responses = list(pool.map(request, [False, True, False]))
            self.assertEqual(responses, [200, 200, 200])
            callback.return_value.initialize_transaction.assert_not_called()
        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(attempt.status, "successful")
        self.assertEqual(PaymentAttempt.objects.count(), 1)


class _CacheIsolatedResult(TextTestResult):
    def startTest(self, test):
        # Django rolls back database fixtures, not DRF's in-memory throttle
        # history. Keep independent test cases independent without disabling
        # throttles or changing their limits inside any test.
        if settings.CACHES["default"]["BACKEND"] != "django.core.cache.backends.locmem.LocMemCache":
            raise RuntimeError("Callback regression runner requires an isolated local memory cache.")
        cache.clear()
        super().startTest(test)


class CallbackRegressionRunner(DiscoverRunner):
    def get_resultclass(self):
        return _CacheIsolatedResult
