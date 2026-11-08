"""Use the real settlement service and existing payment fixtures; no provider I/O."""
from datetime import timedelta
from unittest.mock import patch
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from . import tests as existing
from .models import HousingJob, PaymentAttempt, PortalAccount, PortalAccountBooking
from .payment_views import _apply_verified_transaction
from .registration_accounts import process_verification_delivery
from .test_housing_phase2 import HousingFixtures
from .housing_queue import discover, claim, process_claim


@override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class SettlementFollowupTests(APITestCase):
    setUp = existing.PaymentApiTests.setUp
    create_pending_attempt = existing.PaymentApiTests.create_pending_attempt
    provider_result = existing.PaymentApiTests.provider_result

    def test_duplicate_settlement_enqueues_once_and_preserves_held_work(self):
        attempt = self.create_pending_attempt()
        evidence = self.provider_result(attempt.reference)
        _apply_verified_transaction(attempt.pk, evidence)
        job = HousingJob.objects.get()
        job.state, job.reason = 'held', 'Guardian evidence requires review.'
        job.save()
        _apply_verified_transaction(attempt.pk, evidence)
        self.assertEqual(HousingJob.objects.count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.state, 'held')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.status, 'confirmed')

    def test_invalid_payment_does_not_enqueue(self):
        attempt = self.create_pending_attempt()
        evidence = self.provider_result(attempt.reference, amount=1)
        _apply_verified_transaction(attempt.pk, evidence)
        self.assertFalse(HousingJob.objects.exists())
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, 'paid')

    def test_interrupted_handoff_can_repeat_verification_without_losing_work(self):
        attempt = self.create_pending_attempt()
        evidence = self.provider_result(attempt.reference)
        with patch('dic.payment_followups.HousingJob.objects.get_or_create', side_effect=OperationalError('synthetic')):
            with self.assertRaises(OperationalError):
                _apply_verified_transaction(attempt.pk, evidence)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, 'paid')
        _apply_verified_transaction(attempt.pk, evidence)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(HousingJob.objects.count(), 1)

    def test_housing_policy_delay_does_not_reverse_settlement(self):
        from django.contrib.auth import get_user_model
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        actor = get_user_model().objects.create_user(username='followup-worker', is_staff=True, is_superuser=True)
        # This fixture has no approved housing inventory; the real service holds it.
        self.assertEqual(process_claim(*claim(self.edition.pk, actor), actor), 'held')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.status, 'confirmed')

    def test_email_failure_preserves_account_binding_and_verified_payment(self):
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        account = PortalAccountBooking.objects.get(order=self.order).account
        PortalAccount.objects.filter(pk=account.pk).update(verification_delivery_at=timezone.now())
        with patch('dic.registration_accounts.pending_registration', return_value=True), \
                patch('dic.registration_accounts.deliver_verification', side_effect=RuntimeError('private provider detail')):
            self.assertEqual(process_verification_delivery(account.pk), 'pending')
        account.refresh_from_db()
        self.assertGreater(account.verification_delivery_at, timezone.now())
        self.assertEqual(account.verification_delivery_attempts, 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertTrue(PortalAccountBooking.objects.filter(account=account, order=self.order).exists())
        PortalAccount.objects.filter(pk=account.pk).update(verification_delivery_at=timezone.now()-timedelta(seconds=1))
        with patch('dic.registration_accounts.pending_registration', return_value=True), \
                patch('dic.registration_accounts.deliver_verification') as send:
            self.assertEqual(process_verification_delivery(account.pk), 'sent')
            self.assertEqual(process_verification_delivery(account.pk), 'skipped')
            send.assert_called_once()


class HousingRetryTests(HousingFixtures, TestCase):
    def setUp(self):
        self.initialize()

    def test_transient_failure_is_delayed_and_policy_hold_is_not_reset(self):
        self.participant()
        discover(self.edition.pk, self.actor)
        job_id, token = claim(self.edition.pk, self.actor)
        with patch('dic.housing_queue.allocate_batch', side_effect=OperationalError('private connection details')):
            self.assertEqual(process_claim(job_id, token, self.actor), 'pending')
        self.assertIsNone(claim(self.edition.pk, self.actor))
        HousingJob.objects.filter(pk=job_id).update(retry_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(process_claim(*claim(self.edition.pk, self.actor), self.actor), 'completed')
