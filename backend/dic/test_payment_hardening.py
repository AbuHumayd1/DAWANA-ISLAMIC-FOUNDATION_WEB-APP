import hashlib
import hmac
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection, transaction
from django.db.models.query import QuerySet
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from . import tests as existing
from .models import PaymentAttempt, PaystackWebhookEvent, RegistrationOrder
from .payment_views import (
    _apply_verified_transaction, _mark_initialization_failure, _verify_attempt,
    PaymentProviderUnavailable,
)
from .payments import PaystackTransportError


class Fixtures:
    setUp = existing.PaymentApiTests.setUp
    create_pending_attempt = existing.PaymentApiTests.create_pending_attempt
    provider_result = existing.PaymentApiTests.provider_result
    initialize_url = existing.PaymentApiTests.initialize_url
    verify_url = existing.PaymentApiTests.verify_url


@override_settings(PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock")
class PaymentEvidenceTests(Fixtures, APITestCase):
    def test_invalid_identity_and_environment_never_credit_order(self):
        cases = [
            {"id": value} for value in (None, True, False, 0, -1, "123", 1.5, 10 ** 64)
        ] + [{"domain": value} for value in (None, "live", "TEST", " test ")]
        cases += [{"reference": "other"}, {"amount": True}, {"amount": "1250025"},
                  {"amount": 1}, {"currency": "USD"}, {"currency": "ngn"}]
        for index, override in enumerate(cases):
            with self.subTest(override=override):
                attempt = self.create_pending_attempt(f"DIC-invalid-{index}")
                with patch("dic.payment_views.PaystackClient") as factory:
                    factory.return_value.verify_transaction.return_value = self.provider_result(
                        attempt.reference, **override
                    )
                    response = self.client.post(self.verify_url(attempt.reference), {}, **self.auth)
                self.assertEqual(response.status_code, 200)
                attempt.refresh_from_db()
                self.order.refresh_from_db()
                self.assertEqual(attempt.status, PaymentAttempt.Status.AMOUNT_MISMATCH)
                self.assertIsNone(attempt.provider_transaction_id)
                self.assertEqual(self.order.payment_status, "pending")
                attempt.status = PaymentAttempt.Status.FAILED
                attempt.save(update_fields=["status"])

    def test_status_must_be_exact_success(self):
        for index, value in enumerate(("suc!cess", "SUCCESS", "pending", "failed", None)):
            with self.subTest(status=value):
                attempt = self.create_pending_attempt(f"DIC-status-{index}")
                _apply_verified_transaction(attempt.pk, self.provider_result(
                    attempt.reference, status=value, id=100 + index
                ))
                self.order.refresh_from_db()
                self.assertNotEqual(self.order.payment_status, "paid")
                attempt.refresh_from_db()
                self.assertNotEqual(attempt.status, "successful")
                if value == "suc!cess":
                    self.assertNotEqual(attempt.provider_status, "success")
                attempt.status = "failed"
                attempt.save(update_fields=["status"])

    def test_successful_test_evidence_settles_and_replays(self):
        attempt = self.create_pending_attempt()
        data = self.provider_result(attempt.reference)
        for _ in range(2):
            result, order = _apply_verified_transaction(attempt.pk, data)
            self.assertEqual(result.status, "successful")
            self.assertEqual(order.payment_status, "paid")
            self.assertEqual(order.status, "confirmed")
        self.assertEqual(PaymentAttempt.objects.filter(status="successful").count(), 1)

    def test_recorded_provider_identity_cannot_change(self):
        attempt = self.create_pending_attempt()
        attempt.provider_transaction_id = "55"
        attempt.save(update_fields=["provider_transaction_id"])
        result, order = _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        self.assertEqual(result.failure_code, "provider_transaction_invalid")
        self.assertEqual(result.provider_transaction_id, "55")
        self.assertNotEqual(order.payment_status, "paid")

    def test_late_non_success_and_transport_failure_do_not_revive_superseded(self):
        old = self.create_pending_attempt("DIC-old")
        old.status = "superseded"
        old.save(update_fields=["status"])
        current = self.create_pending_attempt("DIC-current")
        for state in ("pending", "failed"):
            _apply_verified_transaction(old.pk, self.provider_result(old.reference, status=state))
            old.refresh_from_db()
            current.refresh_from_db()
            self.assertEqual(old.status, "superseded")
            self.assertEqual(current.status, "pending")
        provider = Mock()
        provider.verify_transaction.side_effect = PaystackTransportError()
        with self.assertRaises(PaymentProviderUnavailable):
            _verify_attempt(old, provider)
        old.refresh_from_db()
        self.assertEqual(old.status, "superseded")

    def test_late_unacceptable_success_freezes_new_checkout_for_review(self):
        old = self.create_pending_attempt("DIC-old")
        old.status = "superseded"
        old.save(update_fields=["status"])
        current = self.create_pending_attempt("DIC-current")
        result, order = _apply_verified_transaction(old.pk, self.provider_result(old.reference))
        self.assertEqual(result.status, "reconcile")
        self.assertNotEqual(order.payment_status, "paid")
        current.refresh_from_db()
        self.assertEqual(current.status, "superseded")

    def test_stale_failures_preserve_verified_and_review_states(self):
        attempt = self.create_pending_attempt()
        provider = Mock()
        provider.verify_transaction.side_effect = PaystackTransportError()
        for state in ("successful", "duplicate_success", "superseded", "amount_mismatch", "reconcile"):
            with self.subTest(state=state):
                attempt.status = state
                attempt.failure_code = "preserve"
                attempt.save(update_fields=["status", "failure_code"])
                _mark_initialization_failure(attempt.pk, "late_failure", "failed")
                with self.assertRaises(PaymentProviderUnavailable):
                    _verify_attempt(attempt, provider)
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, state)
                self.assertEqual(attempt.failure_code, "preserve")

    def test_non_success_evidence_does_not_clear_reconciliation(self):
        attempt = self.create_pending_attempt()
        for state in ("reconcile", "amount_mismatch", "failed"):
            attempt.status = state
            attempt.failure_code = "preserve"
            attempt.save(update_fields=["status", "failure_code"])
            result, order = _apply_verified_transaction(
                attempt.pk, self.provider_result(attempt.reference, status="pending")
            )
            self.assertEqual(result.status, state)
            self.assertEqual(result.failure_code, "preserve")
            self.assertNotEqual(order.payment_status, "paid")


@override_settings(PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock")
class PaymentConcurrencyTests(Fixtures, APITransactionTestCase):
    def worker(self, operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            return operation()
        finally:
            connection.close()

    def test_initialization_completion_locks_order_before_attempt(self):
        ready = threading.Event()
        finish_provider = threading.Event()
        first_lock = threading.Event()
        queries = []

        def initialize(**kwargs):
            ready.set()
            self.assertTrue(finish_provider.wait(timeout=5))
            return {"reference": kwargs["reference"],
                    "authorization_url": "https://checkout.paystack.com/test-hardening"}

        def observe(execute, sql, params, many, context):
            if finish_provider.is_set() and "FOR UPDATE" in sql and not queries:
                queries.append(sql)
                first_lock.set()
            return execute(sql, params, many, context)

        def initiate():
            with connection.execute_wrapper(observe):
                return APIClient().post(self.initialize_url(), {}, **self.auth).status_code

        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.initialize_transaction.side_effect = initialize
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.worker, initiate)
                self.assertTrue(ready.wait(timeout=5))
                with transaction.atomic():
                    RegistrationOrder.objects.select_for_update().get(pk=self.order.pk)
                    finish_provider.set()
                    self.assertTrue(first_lock.wait(timeout=5))
                    # A settlement holding the order must still be able to lock
                    # the attempt. The original finalizer locks in reverse.
                    PaymentAttempt.objects.select_for_update(nowait=True).get(order=self.order)
                status = future.result(timeout=15)
        self.assertEqual(status, 200)
        self.assertIn('FROM "dic_registrationorder"', queries[0])

    def test_concurrent_provider_identity_claim_credits_only_one_order(self):
        first = self.create_pending_attempt("DIC-first")
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
                                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)
        second_order = RegistrationOrder.objects.get(public_id=response.data["order_id"])
        second = PaymentAttempt.objects.create(
            order=second_order, reference="DIC-second", amount_kobo=first.amount_kobo,
            status="pending", price_revision=second_order.current_price_revision,
        )
        barrier = threading.Barrier(2)
        original = QuerySet.exists

        def synchronized_exists(queryset):
            result = original(queryset)
            if not result and '"provider_transaction_id" =' in str(queryset.query):
                barrier.wait(timeout=5)
            return result

        data = [self.provider_result(a.reference) for a in (first, second)]
        with patch.object(QuerySet, "exists", synchronized_exists):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.worker, lambda a=a, d=d:
                    _apply_verified_transaction(a.pk, d)[0].status)
                    for a, d in zip((first, second), data)]
                states = [f.result(timeout=15) for f in futures]
        self.assertCountEqual(states, ["successful", "amount_mismatch"])
        self.assertEqual(RegistrationOrder.objects.filter(payment_status="paid").count(), 1)
        loser = PaymentAttempt.objects.get(status="amount_mismatch")
        self.assertEqual(loser.failure_code, "provider_transaction_reused")
        self.assertIsNone(loser.provider_transaction_id)

    def test_settlement_during_initialization_is_not_overwritten(self):
        initializing = threading.Event()
        settled = threading.Event()

        def initialize(**kwargs):
            initializing.set()
            if not settled.wait(timeout=5):
                raise AssertionError("Settlement failed to finish during provider call")
            return {"reference": kwargs["reference"],
                    "authorization_url": "https://checkout.paystack.com/test-hardening"}

        def settle():
            self.assertTrue(initializing.wait(timeout=5))
            attempt = PaymentAttempt.objects.get(order=self.order)
            data = self.provider_result(attempt.reference)
            try:
                return _apply_verified_transaction(attempt.pk, data)[0].status
            finally:
                settled.set()

        def initiate():
            return APIClient().post(self.initialize_url(), {}, **self.auth).status_code

        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.initialize_transaction.side_effect = initialize
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(self.worker, initiate)
                b = pool.submit(self.worker, settle)
                self.assertEqual(a.result(timeout=15), 200)
                self.assertEqual(b.result(timeout=15), "successful")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(PaymentAttempt.objects.get().status, "successful")
        self.assertEqual(PaymentAttempt.objects.get().authorization_url, "")

    def test_concurrent_duplicate_webhooks_credit_once(self):
        attempt = self.create_pending_attempt()
        data = self.provider_result(attempt.reference)
        body = json.dumps({"event": "charge.success", "data": {
            "reference": attempt.reference
        }}).encode()
        signature = hmac.new(b"sk_test_unit_mock", body, hashlib.sha512).hexdigest()
        ready = threading.Barrier(2)

        def deliver():
            ready.wait(timeout=5)
            return APIClient().post(
                "/api/v1/dic/payments/paystack/webhook/", body,
                content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature,
            ).status_code

        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.secret_key = "sk_test_unit_mock"
            factory.return_value.verify_transaction.return_value = data
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.worker, deliver) for _ in range(2)]
                self.assertEqual([f.result(timeout=15) for f in futures], [200, 200])
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(PaymentAttempt.objects.filter(status="successful").count(), 1)
        self.assertEqual(PaystackWebhookEvent.objects.count(), 1)
        self.assertEqual(PaystackWebhookEvent.objects.get().processing_status, "processed")

    def test_concurrent_initialization_creates_one_provider_attempt(self):
        ready = threading.Barrier(2)

        def initiate():
            ready.wait(timeout=5)
            response = APIClient().post(self.initialize_url(), {}, **self.auth)
            return response.status_code

        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.initialize_transaction.side_effect = lambda **kwargs: {
                "reference": kwargs["reference"],
                "authorization_url": "https://checkout.paystack.com/test-hardening",
            }
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.worker, initiate) for _ in range(2)]
                statuses = [f.result(timeout=15) for f in futures]
        self.assertIn(200, statuses)
        self.assertTrue(all(s in (200, 400) for s in statuses))
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        factory.return_value.initialize_transaction.assert_called_once()
