import io
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.management import call_command, CommandError
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CampEdition,
    House,
    HouseAllocation,
    Participant,
    PaymentAttempt,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationRecoveryChallenge,
    RegistrationRecoveryGrant,
    RegistrationRecoveryGrantOrder,
    RegistrationRecoveryRateLimit,
)
from .recovery import DevelopmentTestRecoveryAdapter, normalize_phone
from .recovery_views import (
    MAX_CODE_ATTEMPTS,
    MAX_REQUESTS_PER_CONTACT,
    _contact_digest,
    _digest,
)

TEST_RECOVERY_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


class MockSMSAdapter:
    deliveries = []

    def send(self, destination, code):
        self.deliveries.append((destination, code))


@override_settings(
    DIC_EMAIL_RECOVERY_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.test",
    DEFAULT_FROM_EMAIL="registrations@example.test",
    DIC_RECOVERY_DELIVERY_WORKER_ENABLED=True,
    DIC_RECOVERY_ENCRYPTION_KEY=TEST_RECOVERY_ENCRYPTION_KEY,
    DIC_SMS_RECOVERY_ADAPTER="dic.test_recovery.MockSMSAdapter",
)
class RegistrationRecoveryTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.today = timezone.localdate()
        camp_start = self.today + timedelta(days=30)
        self.edition = CampEdition.objects.create(
            name="Recovery Test Camp",
            year=self.today.year,
            camp_start_date=camp_start,
            camp_end_date=camp_start + timedelta(days=6),
            registration_open_date=self.today - timedelta(days=1),
            registration_close_date=self.today + timedelta(days=1),
            registration_status=CampEdition.RegistrationStatus.OPEN,
            is_active=True,
        )
        self.category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Recovery Test Category",
            fee_ngn=Decimal("12500.25"),
        )
        MockSMSAdapter.deliveries.clear()
        self.client = APIClient()

    def participant(self, *, name="Test Participant", email="participant@example.test", phone="+2348012345678"):
        return {
            "category_id": self.category.pk,
            "full_name": name,
            "address": "Fictional recovery test address",
            "phone": phone,
            "email": email,
            "date_of_birth": (self.today - timedelta(days=20 * 365)).isoformat(),
            "sex": Participant.Sex.MALE,
            "height_cm": "175",
            "weight_kg": "70",
            "academic_status": Participant.AcademicStatus.TERTIARY,
            "occupation": Participant.Occupation.BUSINESS,
            "marital_status": Participant.MaritalStatus.SINGLE,
        }

    def create_order(self, *, email="participant@example.test", phone="+2348012345678", name="Test Participant"):
        response = self.client.post(
            reverse("dic:order-create"),
            {"participants": [self.participant(name=name, email=email, phone=phone)]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = RegistrationOrder.objects.get(public_id=response.data["order_id"])
        return order, response.data["access_token"]

    def start(self, *, channel="email", contact="participant@example.test", client=None):
        return (client or self.client).post(
            reverse("dic:recovery-challenge"),
            {"channel": channel, "contact": contact},
            format="json",
        )

    def read_code(self, mock_send):
        message = mock_send.call_args.kwargs["message"]
        return re.search(r"\b(\d{6})\b", message).group(1)

    def process_deliveries(self):
        call_command("send_dic_recovery_messages", stdout=io.StringIO())

    @patch("dic.recovery.send_mail", return_value=1)
    def test_recovered_unpaid_early_order_requires_accepted_repricing(self, mock_send):
        cutoff = timezone.now() + timedelta(minutes=5)
        self.edition.early_bird_cutoff_at = cutoff
        self.edition.save(update_fields=("early_bird_cutoff_at",))
        self.category.early_bird_fee_ngn = Decimal("10000.00")
        self.category.save(update_fields=("early_bird_fee_ngn",))
        order, _ = self.create_order()
        item = order.items.get()
        self.assertEqual(order.total_amount_ngn, Decimal("10000.00"))

        self.edition.early_bird_cutoff_at = timezone.now() - timedelta(seconds=1)
        self.edition.save(update_fields=("early_bird_cutoff_at",))
        started = self.start()
        self.assertEqual(started.status_code, 202)
        self.process_deliveries()
        code = self.read_code(mock_send)
        verified = self.verify(started.data["challenge_id"], code)
        self.assertEqual(verified.status_code, 200)

        listed = self.client.get(
            reverse("dic:recovery-orders"),
            HTTP_AUTHORIZATION=f"Bearer {verified.data['recovery_grant']}",
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.data["orders"][0]["total_amount_ngn"],
            "10000.00",
        )
        restored = self.client.post(
            reverse("dic:recovery-restore-order", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {verified.data['recovery_grant']}",
        )
        self.assertEqual(restored.status_code, 200)
        token = restored.data["access_token"]

        stale_payment = self.client.post(
            reverse("dic:payment-initialize", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(stale_payment.status_code, 409)
        self.assertTrue(stale_payment.data["repricing_required"])
        accepted = self.client.post(
            reverse("dic:pricing-accept", args=[order.public_id]),
            {"quote": stale_payment.data["quote"]},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data["total_amount_ngn"], "12500.25")
        self.assertEqual(order.payment_status, RegistrationOrder.PaymentStatus.PENDING)
        self.assertEqual(order.total_amount_ngn, Decimal("12500.25"))
        self.assertEqual(item.fee_snapshot_ngn, Decimal("10000.00"))
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 0)

    def verify(self, challenge_id, code, *, client=None):
        return (client or self.client).post(
            reverse("dic:recovery-verify", args=[challenge_id]),
            {"code": code},
            format="json",
        )

    @patch("dic.recovery.send_mail", return_value=1)
    def test_email_recovery_scopes_order_and_rotates_access_token(self, mock_send):
        order, old_token = self.create_order()

        with patch(
            "dic.recovery_views._matching_orders",
            side_effect=AssertionError("order matching must run outside the API request"),
        ):
            start = self.start(contact=" PARTICIPANT@EXAMPLE.TEST ")

        self.assertEqual(start.status_code, 202)
        self.assertNotIn("access_token", start.data)
        self.assertNotIn("orders", start.data)
        self.assertNotIn("code", start.data)
        mock_send.assert_not_called()
        challenge = RegistrationRecoveryChallenge.objects.get(pk=start.data["challenge_id"])
        self.assertEqual(
            challenge.delivery_status,
            RegistrationRecoveryChallenge.DeliveryStatus.QUEUED,
        )
        self.assertNotIn("participant@example.test", challenge.encrypted_delivery_payload)
        self.assertFalse(challenge.orders.exists())
        self.process_deliveries()
        challenge.refresh_from_db()
        code = self.read_code(mock_send)
        self.assertNotIn(code, challenge.code_digest)
        self.assertEqual(challenge.delivery_status, RegistrationRecoveryChallenge.DeliveryStatus.SENT)
        self.assertEqual(list(challenge.orders.all()), [order])
        mock_send.assert_called_once()
        self.process_deliveries()
        mock_send.assert_called_once()

        verified = self.verify(challenge.pk, code)

        self.assertEqual(verified.status_code, 200)
        self.assertNotIn("orders", verified.data)
        self.assertNotIn(code, str(verified.data))
        grant_token = verified.data["recovery_grant"]
        listed = self.client.get(
            reverse("dic:recovery-orders"),
            HTTP_AUTHORIZATION=f"Bearer {grant_token}",
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["order_id"] for row in listed.data["orders"]], [str(order.public_id)])
        self.assertNotIn("email", str(listed.data))

        restored = self.client.post(
            reverse("dic:recovery-restore-order", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {grant_token}",
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["order"]["payment_status"], "pending")
        self.assertEqual(restored.data["order"]["total_amount_ngn"], "12500.25")
        self.assertNotEqual(restored.data["access_token"], old_token)
        duplicate_restore = self.client.post(
            reverse("dic:recovery-restore-order", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {grant_token}",
        )
        self.assertEqual(duplicate_restore.status_code, 404)
        self.assertIsNotNone(
            RegistrationRecoveryGrantOrder.objects.get(order=order).redeemed_at
        )
        old_access = self.client.get(
            reverse("dic:order-detail", args=[order.public_id]),
            HTTP_AUTHORIZATION=f"Bearer {old_token}",
        )
        new_access = self.client.get(
            reverse("dic:order-detail", args=[order.public_id]),
            HTTP_AUTHORIZATION=f"Bearer {restored.data['access_token']}",
        )
        self.assertEqual(old_access.status_code, 404)
        self.assertEqual(new_access.status_code, 200)
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(HouseAllocation.objects.exists())

    @patch("dic.recovery.send_mail", return_value=1)
    def test_sms_recovery_normalizes_nigerian_contact(self, mock_send):
        self.create_order()

        response = self.start(channel="sms", contact="0801 234 5678")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(MockSMSAdapter.deliveries, [])
        self.process_deliveries()
        self.assertEqual(MockSMSAdapter.deliveries[0][0], "+2348012345678")
        code = MockSMSAdapter.deliveries[0][1]
        self.assertEqual(self.verify(response.data["challenge_id"], code).status_code, 200)
        mock_send.assert_not_called()
        self.assertEqual(normalize_phone("2348012345678"), "+2348012345678")
        self.assertEqual(normalize_phone("+234 0801 234 5678"), "+2348012345678")

    def test_development_test_adapter_uses_only_an_explicit_test_sink(self):
        deliveries = []
        adapter = DevelopmentTestRecoveryAdapter(
            lambda destination, code: deliveries.append((destination, code))
        )

        adapter.send("test@example.test", "123456")

        self.assertEqual(deliveries, [("test@example.test", "123456")])

    @override_settings(
        DIC_WHATSAPP_ACCESS_TOKEN="",
        DIC_WHATSAPP_PHONE_NUMBER_ID="",
        DIC_WHATSAPP_OTP_TEMPLATE="",
        DIC_WHATSAPP_SUPPORT_NUMBER="",
    )
    def test_whatsapp_recovery_is_unavailable_without_official_provider(self):
        channels = self.client.get(reverse("dic:recovery-channels"))
        whatsapp = next(item for item in channels.data["channels"] if item["id"] == "whatsapp")
        response = self.start(channel="whatsapp", contact="+2348012345678")

        self.assertFalse(whatsapp["available"])
        self.assertIsNone(channels.data["whatsapp_support_url"])
        self.assertEqual(response.status_code, 503)
        self.assertFalse(RegistrationRecoveryChallenge.objects.exists())

    @override_settings(
        DIC_RECOVERY_DELIVERY_WORKER_ENABLED=False,
        DIC_RECOVERY_ENCRYPTION_KEY="",
    )
    def test_recovery_channels_are_unavailable_without_delivery_worker(self):
        channels = self.client.get(reverse("dic:recovery-channels"))
        email = next(item for item in channels.data["channels"] if item["id"] == "email")
        response = self.start()

        self.assertFalse(email["available"])
        self.assertEqual(response.status_code, 503)
        self.assertFalse(RegistrationRecoveryChallenge.objects.exists())

    @override_settings(DIC_RECOVERY_ENCRYPTION_KEY="")
    def test_recovery_worker_requires_a_valid_encryption_key(self):
        channels = self.client.get(reverse("dic:recovery-channels"))
        email = next(item for item in channels.data["channels"] if item["id"] == "email")

        self.assertFalse(email["available"])
        with self.assertRaises(CommandError):
            self.process_deliveries()

    @patch("dic.recovery.send_mail", return_value=1)
    def test_unknown_contact_response_is_generic_and_never_sends_code(self, mock_send):
        response = self.start(contact="nobody@example.test")

        self.assertEqual(response.status_code, 202)
        other = self.start(contact="other@example.test")
        self.assertEqual(response.data["message"], other.data["message"])
        mock_send.assert_not_called()
        self.process_deliveries()
        challenge = RegistrationRecoveryChallenge.objects.get(pk=response.data["challenge_id"])
        self.assertEqual(challenge.delivery_status, RegistrationRecoveryChallenge.DeliveryStatus.SUPPRESSED)
        self.assertFalse(challenge.orders.exists())
        self.assertEqual(challenge.encrypted_delivery_payload, "")
        self.assertEqual(
            self.verify(challenge.pk, "123456").status_code,
            400,
        )

    @patch("dic.recovery.send_mail", return_value=1)
    def test_wrong_expired_and_reused_codes_are_rejected(self, mock_send):
        self.create_order()
        response = self.start()
        self.process_deliveries()
        code = self.read_code(mock_send)
        challenge_id = response.data["challenge_id"]

        self.assertEqual(self.verify(challenge_id, "000000").status_code, 400)
        challenge = RegistrationRecoveryChallenge.objects.get(pk=challenge_id)
        self.assertEqual(challenge.attempts, 1)
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=("expires_at",))
        self.assertEqual(self.verify(challenge_id, code).status_code, 400)
        self.assertLess(
            RegistrationRecoveryChallenge.objects.get(pk=challenge_id).expires_at,
            timezone.now(),
        )

        resent = self._resend_after_cooldown(response, mock_send)
        new_code = self.read_code(mock_send)
        verified = self.verify(resent.data["challenge_id"], new_code)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(self.verify(resent.data["challenge_id"], new_code).status_code, 400)

    def _resend_after_cooldown(self, response, mock_send):
        challenge = RegistrationRecoveryChallenge.objects.get(pk=response.data["challenge_id"])
        past = timezone.now() - timedelta(seconds=1)
        RegistrationRecoveryChallenge.objects.filter(pk=challenge.pk).update(
            resend_after=past,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        key = _contact_digest("email", "participant@example.test")
        RegistrationRecoveryRateLimit.objects.filter(
            key_digest=_digest("dic.registration-recovery.rate-limit", f"contact:{key}")
        ).update(cooldown_until=past)
        resent = self.client.post(
            reverse("dic:recovery-resend", args=[challenge.pk]),
            {"channel": "email", "contact": "participant@example.test"},
            format="json",
        )
        self.assertEqual(resent.status_code, 202)
        self.process_deliveries()
        self.assertEqual(mock_send.call_count, 2)
        return resent

    @patch("dic.recovery.send_mail", return_value=1)
    def test_resend_cooldown_and_excessive_verification_attempts(self, mock_send):
        self.create_order()
        response = self.start()
        self.process_deliveries()
        challenge_id = response.data["challenge_id"]
        cooldown = self.client.post(
            reverse("dic:recovery-resend", args=[challenge_id]),
            {"channel": "email", "contact": "participant@example.test"},
            format="json",
        )
        self.assertEqual(cooldown.status_code, 429)

        for attempt in range(MAX_CODE_ATTEMPTS):
            self.assertEqual(self.verify(challenge_id, f"{attempt:06d}").status_code, 400)
        challenge = RegistrationRecoveryChallenge.objects.get(pk=challenge_id)
        self.assertEqual(challenge.attempts, MAX_CODE_ATTEMPTS)
        self.assertIsNotNone(challenge.consumed_at)
        self.assertEqual(RegistrationRecoveryGrant.objects.count(), 0)

    @patch("dic.recovery.send_mail", return_value=1)
    def test_contact_request_limit_is_persistent_and_applies_to_unknown_contacts(self, mock_send):
        contact = "unregistered@example.test"
        for index in range(MAX_REQUESTS_PER_CONTACT):
            response = self.start(contact=contact)
            self.assertEqual(response.status_code, 202)
            digest = _contact_digest("email", contact)
            RegistrationRecoveryRateLimit.objects.filter(
                key_digest=_digest("dic.registration-recovery.rate-limit", f"contact:{digest}")
            ).update(cooldown_until=timezone.now() - timedelta(seconds=1))
        limited = self.start(contact=contact)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(mock_send.call_count, 0)

    @patch("dic.recovery.send_mail", side_effect=OSError("private provider details"))
    def test_delivery_failure_is_not_marked_sent_or_disclosed(self, mock_send):
        self.create_order()
        response = self.start()
        self.process_deliveries()
        challenge = RegistrationRecoveryChallenge.objects.get(pk=response.data["challenge_id"])

        self.assertEqual(response.status_code, 202)
        self.assertEqual(challenge.delivery_status, RegistrationRecoveryChallenge.DeliveryStatus.FAILED)
        self.assertEqual(self.verify(challenge.pk, "123456").status_code, 400)
        self.assertNotIn("private provider details", str(response.data))
        self.assertFalse(mock_send.call_args.kwargs["message"].endswith("private provider details"))

    @patch("dic.recovery.send_mail", return_value=1)
    def test_concurrent_delivery_workers_send_a_queued_code_once(self, mock_send):
        self.create_order()
        response = self.start()

        def process():
            close_old_connections()
            try:
                self.process_deliveries()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: process(), range(2)))

        mock_send.assert_called_once()
        challenge = RegistrationRecoveryChallenge.objects.get(
            pk=response.data["challenge_id"]
        )
        self.assertEqual(
            challenge.delivery_status,
            RegistrationRecoveryChallenge.DeliveryStatus.SENT,
        )

    @patch("dic.recovery.send_mail", return_value=1)
    def test_worker_retries_stale_claimed_delivery_once(self, mock_send):
        self.create_order()
        response = self.start()
        challenge = RegistrationRecoveryChallenge.objects.get(
            pk=response.data["challenge_id"]
        )
        RegistrationRecoveryChallenge.objects.filter(pk=challenge.pk).update(
            delivery_status=RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING,
            delivery_started_at=timezone.now()
            - timedelta(seconds=9 + 60),
        )

        self.process_deliveries()

        mock_send.assert_called_once()
        challenge.refresh_from_db()
        self.assertEqual(
            challenge.delivery_status,
            RegistrationRecoveryChallenge.DeliveryStatus.SENT,
        )
        self.assertEqual(challenge.delivery_attempts, 1)
        self.assertEqual(challenge.encrypted_delivery_payload, "")

    def test_cleanup_removes_expired_recovery_records_and_pending_payloads(self):
        now = timezone.now()
        challenge = RegistrationRecoveryChallenge.objects.create(
            contact_digest=_contact_digest("email", "expired@example.test"),
            channel=RegistrationRecoveryChallenge.Channel.EMAIL,
            code_digest=_digest("dic.registration-recovery.code", "expired"),
            encrypted_delivery_payload="encrypted-test-payload",
            expires_at=now - timedelta(days=2),
            resend_after=now - timedelta(days=2),
            delivery_status=RegistrationRecoveryChallenge.DeliveryStatus.QUEUED,
        )
        RegistrationRecoveryGrant.objects.create(
            token_digest=_digest("dic.registration-recovery.grant", "expired-token"),
            challenge=challenge,
            expires_at=now - timedelta(days=2),
        )
        RegistrationRecoveryRateLimit.objects.create(
            key_digest=_digest("dic.registration-recovery.rate-limit", "expired-bucket"),
            window_started_at=now - timedelta(days=2),
        )
        RegistrationRecoveryRateLimit.objects.filter(
            key_digest=_digest(
                "dic.registration-recovery.rate-limit",
                "expired-bucket",
            )
        ).update(updated_at=now - timedelta(days=2))

        call_command("cleanup_dic_recovery", stdout=io.StringIO())

        self.assertFalse(RegistrationRecoveryChallenge.objects.exists())
        self.assertFalse(RegistrationRecoveryGrant.objects.exists())
        self.assertFalse(RegistrationRecoveryRateLimit.objects.exists())

    @patch("dic.recovery.send_mail", return_value=1)
    def test_verified_contact_can_select_only_its_own_multiple_orders(self, mock_send):
        first, _ = self.create_order(name="First Child")
        second, _ = self.create_order(name="Second Child")
        unrelated, _ = self.create_order(
            name="Unrelated Participant",
            email="unrelated@example.test",
            phone="+2348098765432",
        )
        response = self.start()
        self.process_deliveries()
        code = self.read_code(mock_send)
        verified = self.verify(response.data["challenge_id"], code)
        headers = {"HTTP_AUTHORIZATION": f"Bearer {verified.data['recovery_grant']}"}
        listed = self.client.get(reverse("dic:recovery-orders"), **headers)

        self.assertEqual(
            {row["order_id"] for row in listed.data["orders"]},
            {str(first.public_id), str(second.public_id)},
        )
        forbidden = self.client.post(
            reverse("dic:recovery-restore-order", args=[unrelated.public_id]),
            {},
            format="json",
            **headers,
        )
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(RegistrationOrder.objects.count(), 3)

    @patch("dic.recovery.send_mail", return_value=1)
    def test_paid_order_recovery_reports_backend_payment_status_without_changing_it(self, mock_send):
        order, _ = self.create_order()
        RegistrationOrder.objects.filter(pk=order.pk).update(
            payment_status=RegistrationOrder.PaymentStatus.PAID,
            status=RegistrationOrder.Status.CONFIRMED,
        )
        response = self.start()
        self.process_deliveries()
        code = self.read_code(mock_send)
        verified = self.verify(response.data["challenge_id"], code)
        restored = self.client.post(
            reverse("dic:recovery-restore-order", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {verified.data['recovery_grant']}",
        )

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["order"]["payment_status"], "paid")
        self.assertEqual(restored.data["order"]["status"], "confirmed")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        self.assertFalse(PaymentAttempt.objects.exists())
        self.assertFalse(HouseAllocation.objects.exists())

    @patch("dic.recovery.send_mail", return_value=1)
    def test_admin_revoked_order_access_cannot_be_bypassed_by_recovery(self, mock_send):
        order, _ = self.create_order()
        order.access_token_revoked_at = timezone.now()
        order.save(update_fields=("access_token_revoked_at",))
        response = self.start()
        self.process_deliveries()
        verified = self.verify(response.data["challenge_id"], self.read_code(mock_send))
        restored = self.client.post(
            reverse("dic:recovery-restore-order", args=[order.public_id]),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {verified.data['recovery_grant']}",
        )
        self.assertEqual(restored.status_code, 404)

    @patch("dic.recovery.send_mail", return_value=1)
    def test_grants_expire_and_are_required_for_order_retrieval(self, mock_send):
        order, _ = self.create_order()
        response = self.start()
        self.process_deliveries()
        code = self.read_code(mock_send)
        verified = self.verify(response.data["challenge_id"], code)
        no_grant = self.client.get(reverse("dic:recovery-orders"))
        self.assertEqual(no_grant.status_code, 404)
        grant = RegistrationRecoveryGrant.objects.get()
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save(update_fields=("expires_at",))
        expired = self.client.get(
            reverse("dic:recovery-orders"),
            HTTP_AUTHORIZATION=f"Bearer {verified.data['recovery_grant']}",
        )
        self.assertEqual(expired.status_code, 404)
        self.assertTrue(order.items.exists())

    @patch("dic.recovery.send_mail", return_value=1)
    def test_concurrent_verification_redeems_one_code_once(self, mock_send):
        order, _ = self.create_order()
        response = self.start()
        self.process_deliveries()
        code = self.read_code(mock_send)
        challenge_id = response.data["challenge_id"]

        def redeem():
            close_old_connections()
            client = APIClient()
            try:
                return client.post(
                    reverse("dic:recovery-verify", args=[challenge_id]),
                    {"code": code},
                    format="json",
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: redeem(), range(2)))

        self.assertEqual(sorted(statuses), [200, 400])
        self.assertEqual(RegistrationRecoveryGrant.objects.count(), 1)
        self.assertEqual(RegistrationOrder.objects.filter(pk=order.pk).count(), 1)
