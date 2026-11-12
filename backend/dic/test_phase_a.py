"""Synthetic Phase A integration and PostgreSQL race regression coverage."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from threading import Barrier
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import override_settings, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.test import APITestCase, APITransactionTestCase, APIRequestFactory, APIClient
from . import tests as fixtures
from . import portal_accounts as accounts
from . import order_lifecycle as lifecycle
from .models import (RegistrationOrder, PortalAccountBooking, ParticipantPortalGrant,
    OrderExpiry, OrderExpiryPolicy, PaymentResolution, PaymentAttempt, DICAdminAuditEvent)
from .payment_views import _apply_verified_transaction, PaymentProviderUnavailable
from .payment_resolution import resolve
from .serializers import RegistrationCredentialsSerializer


class ParticipantPolicyTests(SimpleTestCase):
    def test_any_nonempty_password_and_preserved_spaces(self):
        user = get_user_model()(username='ordinary')
        for secret in ('x', 'password', '123', '!@', ' ', ' two words '):
            accounts.password_policy(secret, user)
            form = RegistrationCredentialsSerializer(data=dict(username='Parent Name', mode='create',
                password=secret, password_confirmation=secret))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.validated_data['password'], secret)
            user.set_password(secret)
            self.assertNotEqual(user.password, secret)
            self.assertTrue(user.check_password(secret))
        for secret in ('', 'x'*129, None):
            with self.assertRaises(ValidationError):
                accounts.password_policy(secret, user)

    def test_staff_validators_remain_enabled_and_common_password_rejected(self):
        with self.assertRaises(DjangoValidationError):
            validate_password('password', get_user_model()(username='staff', is_staff=True))
        with self.assertRaises(DjangoValidationError):
            validate_password('x', get_user_model()(username='staff', is_staff=True))

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_real_django_password_hash_for_one_character(self):
        user = get_user_model()(username='ordinary')
        user.set_password('x')
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
        self.assertTrue(user.check_password('x'))
        self.assertFalse(user.check_password('y'))


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class PhaseATests(APITestCase):
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def setUp(self):
        cache.clear()
        fixtures.PaymentApiTests.setUp(self)

    def manager(self):
        return get_user_model().objects.create_superuser(username='lifecycle-owner', password='synthetic-owner-password')

    def activate(self):
        actor = self.manager()
        lifecycle.activate(actor)
        return actor

    def age(self, hours=25):
        RegistrationOrder.objects.filter(pk=self.order.pk).update(created_at=timezone.now()-timedelta(hours=hours))
        self.order.refresh_from_db()

    def another(self, **credentials):
        payload = deepcopy(self.order_payload)
        payload['portal_account'].update({'mode': 'existing', **credentials})
        return self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def late(self):
        self.age()
        actor = self.activate()
        attempt = self.create_pending_attempt()
        data = self.provider_result(attempt.reference)
        _apply_verified_transaction(attempt.pk, data)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), ('reconcile', 'order_expired'))
        return actor, attempt, data

    def test_multiple_orders_same_contact_existing_account_wrong_password_and_mismatch(self):
        for _ in range(2):
            response = self.another()
            self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(PortalAccountBooking.objects.values('account_id').distinct().count(), 1)
        self.assertEqual(PortalAccountBooking.objects.count(), 3)
        response = self.another(password='wrong', password_confirmation='wrong')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(RegistrationOrder.objects.count(), 3)
        payload = deepcopy(self.order_payload)
        payload['portal_account']['mode'] = 'existing'
        payload['primary_registrant']['email'] = 'someone-else@example.test'
        response = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 403)

    def test_create_mode_collision_reserved_and_staff_username_never_convert(self):
        for name in ('synthetic-registrant', 'admin', 'staff login', 'privileged'):
            if name == 'privileged':
                get_user_model().objects.create_superuser(username=name, password='x')
            response = self.another(mode='create', username=name, password='x', password_confirmation='x')
            self.assertIn(response.status_code, (400, 403))
        self.assertEqual(PortalAccountBooking.objects.count(), 1)

    def test_new_short_password_new_natural_username_hashed(self):
        payload = deepcopy(self.order_payload)
        payload['primary_registrant']['email'] = 'another-contact@example.test'
        payload['portal_account'] = dict(mode='create', username='Parent Name', password='x', password_confirmation='x')
        response = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        account = PortalAccountBooking.objects.get(order__public_id=response.data['order_id']).account
        self.assertEqual(account.username_key, 'parent name')
        self.assertTrue(account.user.check_password('x'))
        self.assertNotEqual(account.user.password, 'x')

    def test_expiry_boundary_activation_history_and_idempotency(self):
        self.age()
        self.assertFalse(lifecycle.expired(self.order))
        actor = self.activate()
        boundary = lifecycle.deadline(self.order)
        self.assertFalse(lifecycle.expired(self.order, boundary-timedelta(microseconds=1)))
        self.assertTrue(lifecycle.expired(self.order, boundary))
        self.assertTrue(lifecycle.expired(self.order, boundary+timedelta(microseconds=1)))
        self.assertTrue(lifecycle.record_expiry(self.order.pk, actor))
        self.assertFalse(lifecycle.record_expiry(self.order.pk, actor))
        self.assertEqual(OrderExpiry.objects.count(), 1)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='order_expired').count(), 1)

    def test_historical_paid_and_tutor_exemption_preserved(self):
        actor = self.activate()
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        self.age(48)
        self.assertFalse(lifecycle.record_expiry(self.order.pk, actor))
        self.assertFalse(lifecycle.expired(self.order))
        self.order.registration_basis = 'tutor'
        self.assertFalse(lifecycle.expired(self.order))
        self.assertFalse(lifecycle.metadata(self.order)['enforced'])

    def test_late_delivery_timely_payment_and_duplicate_credit(self):
        self.age()
        actor = self.activate()
        attempt = self.create_pending_attempt()
        lifecycle.record_expiry(self.order.pk, actor)
        data = self.provider_result(attempt.reference, paid_at=(lifecycle.deadline(self.order)-timedelta(seconds=1)).isoformat())
        for _ in range(2):
            _apply_verified_transaction(attempt.pk, data)
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ('confirmed', 'paid'))
        self.assertEqual(PaymentAttempt.objects.filter(status='successful').count(), 1)

    def test_missing_ambiguous_and_boundary_payment_requires_reconciliation(self):
        self.age()
        self.activate()
        attempt = self.create_pending_attempt()
        for stamp in (None, '2026-11-12T12:00:00', (timezone.now()+timedelta(days=1)).isoformat(), lifecycle.deadline(self.order).isoformat()):
            _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference, paid_at=stamp))
            self.order.refresh_from_db(); attempt.refresh_from_db()
            self.assertNotEqual(self.order.payment_status, 'paid')
            self.assertEqual(attempt.status, 'reconcile')

    def test_inflight_attempt_preserved_and_new_initialization_denied(self):
        self.age()
        actor = self.activate()
        attempt = self.create_pending_attempt()
        lifecycle.record_expiry(self.order.pk, actor)
        self.assertEqual(OrderExpiry.objects.get().evidence_state, 'verification_required')
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'pending')
        with patch('dic.payment_views.PaystackClient') as client:
            response = self.client.post(reverse('dic:payment-initialize', args=[self.order.public_id]), {}, format='json', **self.auth)
            self.assertEqual(response.status_code, 400)
            client.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_preview_is_readonly_activation_and_interrupted_retry(self):
        self.another()
        RegistrationOrder.objects.update(created_at=timezone.now()-timedelta(hours=25))
        actor = self.manager()
        before = DICAdminAuditEvent.objects.count()
        call_command('expire_dic_orders', dry_run=True, stdout=StringIO())
        self.assertFalse(OrderExpiryPolicy.objects.exists())
        self.assertEqual(DICAdminAuditEvent.objects.count(), before)
        actual = lifecycle.record_expiry
        calls = []
        def interrupt(pk, who):
            calls.append(pk)
            if len(calls) == 2:
                raise RuntimeError('synthetic interruption')
            return actual(pk, who)
        with patch('dic.order_lifecycle.record_expiry', side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                call_command('expire_dic_orders', activate=True, apply=True, actor=actor.pk,
                    database_name=connection.settings_dict['NAME'], stdout=StringIO())
        call_command('expire_dic_orders', apply=True, actor=actor.pk,
            database_name=connection.settings_dict['NAME'], stdout=StringIO())
        self.assertEqual(OrderExpiry.objects.count(), 2)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='order_expiry_activated').count(), 1)

    def test_archive_list_default_hidden_detail_access_and_unauthorized_resolution(self):
        self.age(); actor = self.activate()
        self.client.force_authenticate(actor)
        response = self.client.get(reverse('dic:operations-registrations'))
        self.assertEqual(response.data['count'], 0)
        response = self.client.get(reverse('dic:operations-registrations'), {'archive': 'expired'})
        self.assertEqual(response.data['count'], 1)
        response = self.client.get(reverse('dic:operations-registration-detail', args=[self.order.public_id]))
        self.assertEqual(response.status_code, 200, response.data)
        outsider = get_user_model().objects.create_user(username='ordinary-user', password='x')
        with self.assertRaises(PermissionDenied):
            lifecycle.require_manager(outsider)

    def test_credential_recovery_pending_and_expired_no_dashboard_session_csrf(self):
        payload = dict(identifier='synthetic-registrant', password='River-Cedar!Sparrow-84')
        response = self.client.post(reverse('dic:portal-order-recovery'), payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['orders']), 1)
        self.assertFalse(ParticipantPortalGrant.objects.exists())
        self.age(); self.activate()
        response = self.client.post(reverse('dic:portal-order-recovery'), payload, format='json')
        self.assertTrue(response.data['orders'][0]['order']['lifecycle']['expired'])
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('dic:portal-order-recovery'), payload, format='json').status_code, 403)
        response = self.client.post(reverse('dic:portal-order-recovery'), {**payload, 'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_reinstatement_reverified_idempotent_and_entitlement(self):
        actor, attempt, evidence = self.late()
        key = uuid.uuid4()
        with patch('dic.payments.PaystackClient.verify_transaction', return_value=evidence):
            first = resolve(actor, attempt.reference, key, 'reinstate', 'Verified late payment accepted')
            again = resolve(actor, attempt.reference, key, 'reinstate', 'Verified late payment accepted')
        self.assertEqual(first.pk, again.pk)
        self.order.refresh_from_db()
        self.assertTrue(accounts.booking_eligible(self.order))
        with self.assertRaises(ValidationError):
            resolve(actor, attempt.reference, key, 'reinstate', 'different reason')

    def test_refund_intent_is_not_completion_processed_matching_refund_only(self):
        actor, attempt, evidence = self.late()
        resolve(actor, attempt.reference, uuid.uuid4(), 'refund_requested', 'Owner requested refund')
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, 'refunded')
        data = dict(id=123, transaction=int(attempt.provider_transaction_id), amount=attempt.amount_kobo,
            currency='NGN', domain='test', status='pending', refunded_at=timezone.now().isoformat())
        with patch('dic.payments.PaystackClient.verify_refund', return_value=data):
            with self.assertRaises(ValidationError):
                resolve(actor, attempt.reference, uuid.uuid4(), 'refund_confirmed', 'Verify refund', '123')
        data['status'] = 'processed'
        with patch('dic.payments.PaystackClient.verify_refund', return_value=data):
            resolve(actor, attempt.reference, uuid.uuid4(), 'refund_confirmed', 'Verify refund', '123')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'refunded')
        self.assertFalse(accounts.booking_eligible(self.order))
        self.assertEqual(PaymentResolution.objects.count(), 2)

    def test_prior_paid_booking_keeps_access_while_additional_order_is_unpaid_or_expired(self):
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        response = self.another()
        self.assertEqual(response.status_code, 201)
        account = PortalAccountBooking.objects.get(order=self.order).account
        self.assertEqual([row.pk for row in accounts.linked_orders(account)], [self.order.pk])
        self.activate()
        RegistrationOrder.objects.exclude(pk=self.order.pk).update(created_at=timezone.now()-timedelta(hours=30))
        self.assertEqual([row.pk for row in accounts.linked_orders(account)], [self.order.pk])

    def test_short_common_and_space_password_reset_and_staff_reviewed_recovery(self):
        from types import SimpleNamespace
        from .credential_transition import issue, consume
        actor = self.manager()
        account = PortalAccountBooking.objects.get(order=self.order).account
        proof = SimpleNamespace(channel='email', contact_digest=account.contact_digest)
        for secret in ('x', 'password', ' '):
            with patch.object(accounts, 'fresh_otp', return_value=(proof, [self.order])):
                updated = accounts.reset_password(object(), secret)
            self.assertTrue(updated.user.check_password(secret))
            token = issue(actor, self.order.public_id, 'Synthetic reviewed ownership case', 'synthetic-owner-password')
            consume(token, 'synthetic-registrant', secret)
            account.refresh_from_db(); account.user.refresh_from_db()
            self.assertTrue(account.user.check_password(secret))
        self.assertFalse(ParticipantPortalGrant.objects.exists())

    def test_django_admin_participant_password_policy_isolated_from_staff(self):
        from accounts.participant_admin import ParticipantAwarePasswordChangeForm
        user = PortalAccountBooking.objects.get(order=self.order).account.user
        for secret in ('x', 'password', ' '):
            form = ParticipantAwarePasswordChangeForm(user, data=dict(password1=secret, password2=secret, usable_password='true'))
            self.assertTrue(form.is_valid(), form.errors)
        form = ParticipantAwarePasswordChangeForm(user, data=dict(password1='', password2='', usable_password='true'))
        self.assertFalse(form.is_valid())
        staff = self.manager()
        form = ParticipantAwarePasswordChangeForm(staff, data=dict(password1='x', password2='x', usable_password='true'))
        self.assertFalse(form.is_valid())

    def test_resolution_endpoint_rejects_unprivileged_staff_and_missing_csrf(self):
        actor, attempt, _ = self.late()
        url = reverse('dic:payment-resolution', args=[attempt.reference])
        outsider = get_user_model().objects.create_user(username='ordinary-staff', password='x', is_staff=True)
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 403)
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(actor)
        self.assertEqual(csrf_client.post(url, dict(request_id=str(uuid.uuid4()), decision='refund_requested', reason='Synthetic review'), format='json').status_code, 403)


class PhaseAConcurrencyTests(APITransactionTestCase):
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def setUp(self):
        cache.clear()
        fixtures.PaymentApiTests.setUp(self)

    def test_expiry_racing_timely_settlement_preserves_paid_entitlement(self):
        self.assertEqual(connection.vendor, 'postgresql', 'This regression requires disposable PostgreSQL.')
        actor = get_user_model().objects.create_superuser(username='race-owner', password='x')
        lifecycle.activate(actor)
        RegistrationOrder.objects.filter(pk=self.order.pk).update(created_at=timezone.now()-timedelta(hours=25))
        self.order.refresh_from_db()
        attempt = self.create_pending_attempt()
        evidence = self.provider_result(attempt.reference, paid_at=(lifecycle.deadline(self.order)-timedelta(seconds=1)).isoformat())
        barrier = Barrier(2)
        def worker(expire):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if expire:
                    lifecycle.record_expiry(self.order.pk, get_user_model().objects.get(pk=actor.pk))
                else:
                    _apply_verified_transaction(attempt.pk, evidence)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, flag) for flag in (True, False)]
            for future in futures:
                future.result(timeout=30)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertTrue(accounts.booking_eligible(self.order))
