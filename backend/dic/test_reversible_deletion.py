from copy import deepcopy
from unittest.mock import patch
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import RegistrationOrder, PaymentAttempt, DICAdminAuditEvent, PortalAccountBooking, CampCheckIn
from .payment_views import _apply_verified_transaction
from .registration_cleanup import is_deleted, deleted_orders
from .participant_services import ensure_enrollment, eligibility


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class ReversibleDeletionTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def manager(self):
        actor = get_user_model().objects.create_superuser('trash-manager', 'manager@example.test', 'synthetic-only')
        self.client.force_login(actor)
        return actor

    def act(self, name, confirmation=None, reason='Selected synthetic test'):
        return self.client.post(reverse('dic:'+name, args=[self.order.public_id]),
            {'confirmation': confirmation or str(self.order.public_id), 'reason': reason}, format='json')

    def failed(self):
        attempt = self.create_pending_attempt('verified-failed-trash')
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference, status='failed', paid_at=None))
        self.order.refresh_from_db()
        return attempt

    def test_delete_is_separate_durable_trash_state_not_cancel_or_archive(self):
        actor = self.manager()
        item_id = self.order.items.get().pk
        binding_id = PortalAccountBooking.objects.get(order=self.order).pk
        denied = self.act('operations-registration-delete', confirmation='wrong')
        self.assertEqual(denied.status_code, 400)
        self.assertFalse(is_deleted(self.order))
        rejected = DICAdminAuditEvent.objects.get(action='registration_trashed_rejected')
        self.assertEqual(rejected.details['outcome'], 'rejected')
        response = self.act('operations-registration-delete')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIs(response.data['reversible'], True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertTrue(is_deleted(self.order))
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(self.order.items.get().pk, item_id)
        self.assertTrue(PortalAccountBooking.objects.filter(pk=binding_id).exists())
        for view in ('active', 'all', 'expired'):
            self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': view}).data['count'], 0)
        trash = self.client.get(reverse('dic:operations-registrations'), {'archive': 'trash'}).data
        self.assertEqual(trash['count'], 1)
        row = trash['results'][0]
        self.assertEqual(row['record_state'], 'deleted')
        self.assertTrue(row['restore']['eligible'])
        self.assertIsNotNone(row['deleted_at'])
        self.assertEqual(self.client.get(reverse('dic:operations-participants')).data['count'], 0)
        event = DICAdminAuditEvent.objects.get(action='registration_trashed')
        self.assertEqual(event.actor_id, actor.pk)
        self.assertEqual(event.details['actor_username'], actor.username)
        self.assertEqual(event.details['reference'], str(self.order.public_id))
        self.assertEqual(event.details['outcome'], 'success')
        self.assertIsNotNone(event.created_at)
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='registration_test_archived').exists())

    def test_verified_failed_attempt_can_be_deleted_and_restored_with_evidence(self):
        attempt = self.failed()
        self.manager()
        response = self.act('operations-registration-delete')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(is_deleted(self.order))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'failed')
        self.assertEqual(attempt.reference, 'verified-failed-trash')
        self.assertEqual(self.client.post(reverse('dic:payment-initialize', args=[self.order.public_id]), {}, format='json', **self.auth).status_code, 404)
        self.assertEqual(self.act('operations-registration-restore-deleted').status_code, 200)
        self.assertFalse(is_deleted(self.order))
        self.assertEqual(self.client.get(reverse('dic:operations-registrations')).data['count'], 1)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': 'trash'}).data['count'], 0)
        self.assertEqual(self.client.post(reverse('dic:payment-initialize', args=[self.order.public_id]), {}, format='json', **self.auth).status_code, 404)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='registration_restored', details__outcome='success').exists())

    def test_late_success_retains_transaction_but_never_reactivates_or_grants_benefits(self):
        attempt = self.failed()
        enrollment = ensure_enrollment(self.order.items.get().pk)
        self.manager()
        self.assertEqual(self.act('operations-registration-delete').status_code, 200)
        for _ in range(2):
            _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        self.order.refresh_from_db(); attempt.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertNotEqual(self.order.payment_status, 'paid')
        self.assertTrue(is_deleted(self.order))
        self.assertEqual(attempt.provider_status, 'success')
        self.assertEqual(attempt.status, 'reconcile')
        self.assertEqual(attempt.failure_code, 'deleted_registration_payment')
        self.assertIsNotNone(attempt.provider_paid_at)
        self.assertFalse(eligibility(enrollment)['eligible'])
        self.assertEqual(eligibility(enrollment)['code'], 'registration_deleted')
        self.assertEqual(self.act('operations-registration-restore-deleted').status_code, 400)
        self.assertTrue(is_deleted(self.order))
        self.assertEqual(self.client.get(reverse('dic:operations-registrations')).data['count'], 0)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='registration_restored_rejected').exists())

    def test_unresolved_mismatched_paid_and_checked_in_records_cannot_be_deleted(self):
        attempt = self.create_pending_attempt('not-conclusive')
        self.manager()
        for state in ('initializing', 'init_unknown', 'pending', 'verify_pending', 'amount_mismatch', 'reconcile', 'failed'):
            PaymentAttempt.objects.filter(pk=attempt.pk).update(status=state)
            self.assertEqual(self.act('operations-registration-delete').status_code, 400)
            self.assertFalse(is_deleted(self.order))
        PaymentAttempt.objects.filter(pk=attempt.pk).update(status='successful')
        self.assertEqual(self.act('operations-registration-delete').status_code, 400)
        self.assertFalse(is_deleted(self.order))

    def test_archive_and_delete_have_different_payment_and_visibility_semantics(self):
        self.failed(); self.manager()
        self.assertEqual(self.act('operations-registration-archive-test').status_code, 200)
        self.assertFalse(is_deleted(self.order))
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': 'all'}).data['count'], 1)
        self.assertEqual(self.act('operations-registration-delete').status_code, 200)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': 'all'}).data['count'], 0)
        self.assertEqual(self.act('operations-registration-archive-test').status_code, 400)
        self.assertEqual(self.act('operations-registration-restore-deleted').status_code, 200)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations')).data['count'], 1)

    def test_unrelated_shared_receipt_account_stays_active_and_restore_is_permission_guarded(self):
        data = deepcopy(self.order_payload); data['portal_account'].update(mode='create', username='other-owner')
        other = self.client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(other.status_code, 201)
        self.manager(); self.assertEqual(self.act('operations-registration-delete').status_code, 200)
        rows = self.client.get(reverse('dic:operations-registrations')).data['results']
        self.assertEqual([row['id'] for row in rows], [str(other.data['order_id'])])
        viewer = get_user_model().objects.create_user('viewer', password='synthetic-only', is_staff=True)
        viewer.user_permissions.add(*Permission.objects.filter(content_type__app_label='dic', codename__in=('can_view_dic_operations','view_registrationorder')))
        self.client.force_login(viewer)
        self.assertEqual(self.act('operations-registration-restore-deleted').status_code, 403)
        self.assertEqual(self.client.get(reverse('dic:operations-registrations'), {'archive': 'trash'}).status_code, 403)
        self.assertTrue(is_deleted(self.order))
