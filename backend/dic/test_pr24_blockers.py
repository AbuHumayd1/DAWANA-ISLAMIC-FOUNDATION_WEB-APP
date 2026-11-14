from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import RegistrationOrder, PaymentAttempt, DICAdminAuditEvent, CampCheckIn
from .payment_views import _apply_verified_transaction
from .registration_cleanup import payment_cleanup_state, archived_test_orders


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class CleanupAndInitiationTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def manager(self):
        actor = get_user_model().objects.create_superuser('cleanup-manager', 'synthetic@example.test', 'synthetic-only')
        self.client.force_login(actor)
        return actor

    def action(self, name, confirmation=None):
        return self.client.post(reverse('dic:'+name, args=[self.order.public_id]),
            {'confirmation': confirmation or str(self.order.public_id), 'reason': 'Owner selected synthetic test'}, format='json')

    def test_no_attempt_can_be_reversibly_deleted(self):
        self.manager()
        self.assertEqual(payment_cleanup_state(self.order), 'no_payment_attempt')
        self.assertEqual(self.action('operations-registration-delete').status_code, 200)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.order.pk).exists())
        from .registration_cleanup import is_deleted
        self.assertTrue(is_deleted(self.order))

    def test_verified_failure_archives_without_destroying_protected_evidence(self):
        attempt = self.create_pending_attempt('synthetic-verified-failure')
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference, status='failed', paid_at=None))
        self.order.refresh_from_db()
        self.assertEqual(payment_cleanup_state(self.order), 'failed_evidence_retained')
        self.manager()
        from .registration_cleanup import disposal_blocker
        self.assertEqual(disposal_blocker(self.order), '')
        self.assertEqual(self.action('operations-registration-archive-test', 'wrong').status_code, 400)
        response = self.action('operations-registration-archive-test')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.order.pk).exists())
        self.assertTrue(PaymentAttempt.objects.filter(pk=attempt.pk, reference=attempt.reference).exists())
        self.assertTrue(archived_test_orders().filter(pk=self.order.pk).exists())
        self.assertEqual(self.client.get(reverse('dic:operations-registrations')).json()['count'], 0)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': 'all'}).json()['count'], 1)
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 200)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='registration_test_archived').count(), 1)

    def test_mismatch_is_never_conclusive_failure_and_recheck_never_initializes(self):
        attempt = self.create_pending_attempt('synthetic-mismatch')
        invalid = self.provider_result(attempt.reference, status='failed', amount=attempt.amount_kobo+1)
        _apply_verified_transaction(attempt.pk, invalid)
        self.manager()
        self.assertEqual(payment_cleanup_state(self.order), 'reconciliation_required')
        self.assertEqual(self.action('operations-registration-delete').status_code, 400)
        with patch('dic.payments.PaystackClient') as factory:
            factory.return_value.verify_transaction.return_value = invalid
            response = self.action('operations-registration-recheck-payment')
            self.assertEqual(response.status_code, 200, response.data)
            factory.return_value.verify_transaction.assert_called_once_with(attempt.reference)
            factory.return_value.initialize_transaction.assert_not_called()
        self.assertEqual(payment_cleanup_state(self.order), 'reconciliation_required')
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertTrue(PaymentAttempt.objects.filter(pk=attempt.pk, failure_code='provider_data_mismatch').exists())

    def test_late_settlement_of_archived_order_is_preserved_and_returns_to_active(self):
        attempt = self.create_pending_attempt('synthetic-late-settlement')
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference, status='failed', paid_at=None))
        self.manager()
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 200)
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.status, 'confirmed')
        self.assertFalse(archived_test_orders().filter(pk=self.order.pk).exists())
        self.assertEqual(self.client.get(reverse('dic:operations-registrations')).json()['count'], 1)
        self.assertEqual(self.action('operations-registration-delete').status_code, 400)
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 400)

    def test_pending_and_unknown_never_enable_hard_delete(self):
        attempt = self.create_pending_attempt('synthetic-uncertain')
        self.manager()
        for state in ('pending', 'init_unknown', 'verify_pending', 'failed'):
            PaymentAttempt.objects.filter(pk=attempt.pk).update(status=state)
            self.assertEqual(payment_cleanup_state(self.order), 'payment_in_progress_or_unknown')
            self.assertEqual(self.action('operations-registration-delete').status_code, 400)

    def test_authorization_confirmation_and_checkin_protection(self):
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 403)
        actor = self.manager()
        CampCheckIn.objects.create(edition=self.edition, participant=self.order.items.get().participant, checked_in_by=actor)
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 400)
        self.assertEqual(self.action('operations-registration-delete').status_code, 400)
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='registration_test_archived').exists())

    @override_settings(PAYSTACK_SECRET_KEY='')
    def test_authoritative_no_attempt_flag_does_not_require_account_recovery(self):
        url = reverse('dic:payment-initialize', args=[self.order.public_id])
        denied = self.client.post(url, {}, format='json')
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn('payment_not_initiated', denied.data)
        response = self.client.post(url, {}, format='json', **self.auth)
        self.assertEqual(response.status_code, 503, response.data)
        self.assertIs(response.data['payment_not_initiated'], True)
        self.assertFalse(self.order.payment_attempts.exists())

    def test_metadata_does_not_clear_existing_attempt_or_paid_order(self):
        self.create_pending_attempt('existing-init')
        response = self.client.post(reverse('dic:payment-initialize', args=[self.order.public_id]), {}, format='json', **self.auth)
        self.assertIsNot(response.data.get('payment_not_initiated'), True)

    def test_archiving_one_order_does_not_hide_shared_email_registrations(self):
        from copy import deepcopy
        import uuid
        from .models import PortalAccountBooking
        data = deepcopy(self.order_payload)
        data['portal_account'].update(mode='create', username='independent-second-owner')
        response = self.client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        other = RegistrationOrder.objects.get(public_id=response.data['order_id'])
        self.assertNotEqual(PortalAccountBooking.objects.get(order=other).account_id, PortalAccountBooking.objects.get(order=self.order).account_id)
        self.manager()
        self.assertEqual(self.action('operations-registration-archive-test').status_code, 200)
        rows = self.client.get(reverse('dic:operations-registrations')).json()
        self.assertEqual(rows['count'], 1)
        self.assertEqual(rows['results'][0]['id'], str(other.public_id))

    def test_authorized_status_distinguishes_unused_order_from_any_attempt(self):
        from .payment_return import _summary
        self.assertIs(_summary(self.order)['payment_requested'], False)
        self.create_pending_attempt('status-check-attempt')
        self.assertIs(_summary(self.order)['payment_requested'], True)

    def test_provider_recheck_requires_explicit_finance_permission(self):
        from django.contrib.auth.models import Permission
        actor = get_user_model().objects.create_user('non-finance-manager', password='synthetic-only', is_staff=True)
        actor.user_permissions.add(*Permission.objects.filter(content_type__app_label='dic', codename__in=(
            'can_view_dic_operations', 'delete_registrationorder', 'can_manage_registration_access')))
        self.client.force_login(actor)
        with patch('dic.payments.PaystackClient') as provider:
            self.assertEqual(self.action('operations-registration-recheck-payment').status_code, 403)
            provider.assert_not_called()
