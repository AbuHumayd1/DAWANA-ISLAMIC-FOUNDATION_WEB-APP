"""No database or real provider calls: live activation and signature boundaries."""
import hashlib
import hmac
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from .payments import paystack_secret_key, PaystackConfigurationError, verify_webhook_request


@override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_synthetic',
    PAYSTACK_CALLBACK_URL='https://portal.example.test/dic/register/payment-return',
    PAYSTACK_HTTP_TIMEOUT_SECONDS=5, PAYSTACK_LIVE_ENABLED=False, DEBUG=False,
    PAYSTACK_WEBHOOK_SECRET='')
class ProductionPaymentPolicyTests(SimpleTestCase):
    def test_verification_rejects_cross_mode_before_provider_call(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from rest_framework.exceptions import ValidationError
        from .payment_views import _verify_attempt
        provider = Mock()
        with self.settings(PAYSTACK_MODE='live'):
            with self.assertRaises(ValidationError):
                _verify_attempt(SimpleNamespace(provider_mode='test'), provider)
        provider.verify_transaction.assert_not_called()

    def test_test_configuration_remains_supported(self):
        self.assertEqual(paystack_secret_key(), 'sk_test_synthetic')

    def test_live_requires_separate_explicit_activation(self):
        with self.settings(PAYSTACK_MODE='live', PAYSTACK_SECRET_KEY='sk_live_synthetic'):
            with self.assertRaises(PaystackConfigurationError): paystack_secret_key()

    def test_approved_live_requires_matching_key_and_secure_callback(self):
        with self.settings(PAYSTACK_MODE='live', PAYSTACK_SECRET_KEY='sk_live_synthetic', PAYSTACK_LIVE_ENABLED=True):
            self.assertEqual(paystack_secret_key(), 'sk_live_synthetic')
            for overrides in ({'DEBUG': True}, {'PAYSTACK_SECRET_KEY': 'sk_test_synthetic'},
                    {'PAYSTACK_CALLBACK_URL': ''}, {'PAYSTACK_CALLBACK_URL': 'http://portal.example.test/return'}):
                with self.subTest(overrides=list(overrides)), self.settings(**overrides):
                    with self.assertRaises(PaystackConfigurationError): paystack_secret_key()

    def test_test_mode_rejects_live_key_even_with_activation_flag(self):
        with self.settings(PAYSTACK_SECRET_KEY='sk_live_synthetic', PAYSTACK_LIVE_ENABLED=True):
            with self.assertRaises(PaystackConfigurationError): paystack_secret_key()

    def test_legacy_signature_requires_exact_body(self):
        body = b'{"event":"charge.success"}'
        signature = hmac.new(b'sk_test_synthetic', body, hashlib.sha512).hexdigest()
        headers = {'X-Paystack-Signature': signature}
        self.assertTrue(verify_webhook_request(body, headers, 'sk_test_synthetic'))
        self.assertFalse(verify_webhook_request(body+b' ', headers, 'sk_test_synthetic'))
        self.assertFalse(verify_webhook_request(body, {'X-Paystack-Signature': 'invalid'}, 'sk_test_synthetic'))

    @override_settings(PAYSTACK_WEBHOOK_SECRET='whsec_synthetic')
    def test_timestamped_signature_rotation_replay_and_no_downgrade(self):
        body, timestamp = b'{"event":"charge.success"}', '1800000000'
        signature = hmac.new(b'whsec_synthetic', timestamp.encode()+b'.'+body, hashlib.sha512).hexdigest()
        headers = {'Paystack-Signature': 't='+timestamp+',v1=whk_old:'+('0'*128)+',v1=whk_new:'+signature}
        with patch('dic.payments.time', return_value=int(timestamp)):
            self.assertTrue(verify_webhook_request(body, headers, 'unused'))
            self.assertFalse(verify_webhook_request(body+b' ', headers, 'unused'))
            self.assertFalse(verify_webhook_request(body, {'Paystack-Signature': headers['Paystack-Signature']+',t='+timestamp}, 'unused'))
            legacy = hmac.new(b'unused', body, hashlib.sha512).hexdigest()
            self.assertFalse(verify_webhook_request(body, {'X-Paystack-Signature': legacy}, 'unused'))
        with patch('dic.payments.time', return_value=int(timestamp)+301):
            self.assertFalse(verify_webhook_request(body, headers, 'unused'))


@override_settings(PAYSTACK_MODE='live', SETTINGS_MODULE='config.settings.production')
class PaymentEntitlementModeTests(SimpleTestCase):
    """Exercise real entitlement/booking policy with in-memory provider evidence."""

    def setUp(self):
        from datetime import timedelta
        from decimal import Decimal
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from django.utils import timezone
        from . import participant_services as service
        self.service = service
        self.now = timezone.now()
        self.order = NS(pk=1, edition_id=2, registration_basis='paid', status='confirmed',
            payment_status='paid', total_amount_ngn=Decimal('5000.00'), items=Mock(), payment_attempts=Mock())
        self.revision = NS(order_id=1, accepted_at=self.now, early_bird_cutoff_at=None,
            items=Mock())
        self.revision.items.all.return_value = [NS(price_type='regular', early_bird_fee_snapshot_ngn=None)]
        self.order.current_price_revision = self.revision
        self.order.current_price_revision_id = 10
        self.item = NS(pk=3, participant_id=4, order_id=1, order=self.order, category=NS(edition_id=2))
        self.order.items.all.return_value = [self.item]
        self.order.items.count.return_value = 1
        self.order.payment_attempts.exists.return_value = False
        self.enrollment = NS(pk=5, source_item_id=3, participant_id=4, edition_id=2,
            restriction_reason='', source_review_fingerprint='')
        self.attempt = NS(order=self.order, status='successful', provider_mode='live',
            amount_kobo=500000, currency='NGN', provider_status='success',
            provider_reported_amount_kobo=500000, provider_reported_currency='NGN',
            provider_paid_at=self.now + timedelta(seconds=1), verified_at=self.now,
            provider_transaction_id='123456', price_revision=self.revision)
        self.attempts = [self.attempt]
        self.item_manager = self.enterContext(patch.object(service.RegistrationOrderItem, 'objects'))
        self.item_manager.select_related.return_value.get.return_value = self.item
        self.item_manager.filter.return_value.select_related.return_value = [self.item]
        self.enterContext(patch.object(service.RegistrationOrder, 'objects')).select_related.return_value.get.return_value = self.order
        self.payment_manager = self.enterContext(patch.object(service.PaymentAttempt, 'objects'))
        self.payment_manager.filter.side_effect = lambda **criteria: EvidenceRows([
            row for row in self.attempts if evidence_matches(row, criteria)])

    def eligible(self):
        return self.service.eligibility(self.enrollment)['eligible']

    def test_successful_test_payment_is_denied_in_live_mode(self):
        self.attempt.provider_mode = 'test'
        self.assertFalse(self.eligible())

    def test_successful_live_payment_requires_independent_provider_evidence(self):
        self.assertTrue(self.eligible())
        for field, invalid in [('provider_status', 'pending'), ('provider_transaction_id', None),
                ('provider_transaction_id', ''), ('verified_at', None), ('provider_paid_at', None),
                ('amount_kobo', 1), ('provider_reported_amount_kobo', 1),
                ('currency', 'USD'), ('provider_reported_currency', 'USD'), ('price_revision', None)]:
            original = getattr(self.attempt, field)
            with self.subTest(field=field):
                setattr(self.attempt, field, invalid)
                self.assertFalse(self.eligible())
            setattr(self.attempt, field, original)
        self.revision.accepted_at = None
        self.assertFalse(self.eligible())

    def test_mode_switch_does_not_convert_evidence_or_existing_booking_access(self):
        from .portal_accounts import booking_eligible
        self.attempt.provider_mode = 'test'
        with patch('dic.portal_accounts.CampEnrollment.objects') as enrollments:
            enrollments.filter.return_value.first.return_value = self.enrollment
            with self.settings(PAYSTACK_MODE='test', SETTINGS_MODULE='config.settings.staging'):
                self.assertTrue(booking_eligible(self.order))
            self.assertFalse(booking_eligible(self.order))
            self.assertEqual(self.attempt.provider_mode, 'test')
            self.assertEqual(self.attempt.status, 'successful')

    def test_production_test_configuration_never_grants_paid_entitlement(self):
        self.attempt.provider_mode = 'test'
        with self.settings(PAYSTACK_MODE='test'):
            self.assertFalse(self.eligible())
        for mode in ('', None, 'invalid'):
            with self.settings(PAYSTACK_MODE=mode): self.assertFalse(self.eligible())

    def test_existing_password_and_otp_scopes_recheck_entitlement(self):
        from types import SimpleNamespace as NS
        from .participant_api import scoped_orders
        self.attempt.provider_mode = 'test'
        grant = NS(channel='email', contact_digest='synthetic-contact-digest')
        with patch('dic.participant_api.RegistrationOrder.objects') as orders, \
                patch('dic.participant_api.primary_contact_matches', return_value=True), \
                patch('dic.portal_accounts.CampEnrollment.objects') as enrollments, \
                patch('dic.portal_accounts.PortalAccountBooking.objects') as bindings:
            orders.filter.return_value.exclude.return_value.select_related.return_value = [self.order]
            enrollments.filter.return_value.first.return_value = self.enrollment
            bindings.filter.return_value.select_related.return_value = [NS(order=self.order)]
            for mapping in (None, NS(account=NS(pk=8))):
                with self.subTest(password_session=mapping is not None), \
                        patch('dic.portal_accounts.account_session', return_value=mapping):
                    with self.settings(PAYSTACK_MODE='test', SETTINGS_MODULE='config.settings.staging'):
                        self.assertEqual(scoped_orders(grant), [self.order])
                    self.assertEqual(scoped_orders(grant), [])

    def test_tutor_exemption_retains_all_authorization_checks(self):
        from decimal import Decimal
        self.order.registration_basis = 'tutor'
        self.order.payment_status = 'not_required'
        self.order.total_amount_ngn = Decimal(0)
        self.order.current_price_revision_id = None
        with patch('dic.tutor_registration.tutor_entitlement', return_value=True) as authority:
            self.assertTrue(self.eligible())
            with self.settings(PAYSTACK_MODE='test'): self.assertTrue(self.eligible())
            authority.return_value = False
            self.assertFalse(self.eligible())
            authority.return_value = True
            self.order.payment_attempts.exists.return_value = True
            self.assertFalse(self.eligible())
        self.payment_manager.filter.assert_not_called()

    def test_unpaid_cancelled_and_restricted_participants_are_denied(self):
        for status in ('unpaid', 'pending', 'failed', 'refunded', 'not_required'):
            with self.subTest(status=status):
                self.order.payment_status = status
                self.assertFalse(self.eligible())
        self.order.payment_status = 'paid'
        self.order.status = 'cancelled'
        self.assertFalse(self.eligible())
        self.order.status = 'confirmed'
        self.enrollment.restriction_reason = 'authorized review required'
        self.assertFalse(self.eligible())

    def test_non_success_and_reconciliation_evidence_remain_denied(self):
        from types import SimpleNamespace as NS
        for status in ('initializing', 'pending', 'failed', 'init_unknown', 'verify_pending', 'amount_mismatch', 'reconcile', 'duplicate_success'):
            with self.subTest(status=status):
                self.attempt.status = status
                self.assertFalse(self.eligible())
        self.attempt.status = 'successful'
        for status in ('amount_mismatch', 'reconcile'):
            self.attempts = [self.attempt, NS(order=self.order, status=status)]
            self.assertFalse(self.eligible())

    def test_early_bird_payment_time_is_still_enforced(self):
        self.revision.items.all.return_value[0].price_type = 'early_bird'
        self.revision.early_bird_cutoff_at = self.now
        self.assertFalse(self.eligible())


def evidence_matches(row, criteria):
    for name, expected in criteria.items():
        field, _, lookup = name.partition('__')
        actual = getattr(row, field, None)
        if lookup == 'isnull':
            matches = (actual is None) == expected
        elif lookup == 'in':
            matches = actual in expected
        else:
            matches = actual == expected
        if not matches: return False
    return True


class EvidenceRows(list):
    def exclude(self, **criteria):
        return EvidenceRows(row for row in self if not evidence_matches(row, criteria))

    def exists(self):
        return bool(self)
