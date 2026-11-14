from copy import deepcopy
from datetime import date
from unittest.mock import patch
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from . import tests as fixtures
from . import test_operations as operations
from . import test_identity_cards as identity
from .test_participant_portal import PortalFixtures
from .models import (PortalAccountBooking, RegistrationOrder, Participant, CampEnrollment,
    CampCheckIn, DICAdminAuditEvent)
from .participant_services import ensure_enrollment


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class RepeatBookingContactTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp

    @patch('rest_framework.throttling.SimpleRateThrottle.allow_request', return_value=True)
    def test_one_email_creates_100_independent_public_orders_without_linking(self, throttle):
        original = PortalAccountBooking.objects.get(order=self.order).account
        accounts = set()
        for index in range(100):
            payload = deepcopy(self.order_payload)
            payload['portal_account'].update(mode='create', username=f'independent-{index}')
            response = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), REMOTE_ADDR=f'192.0.2.{index+1}')
            self.assertEqual(response.status_code, 201, response.data)
            order = RegistrationOrder.objects.get(public_id=response.data['order_id'])
            binding = PortalAccountBooking.objects.get(order=order)
            self.assertEqual(order.primary_registrant.email, self.order.primary_registrant.email)
            self.assertNotEqual(binding.account_id, original.pk)
            accounts.add(binding.account_id)
        self.assertEqual(len(accounts), 100)
        self.assertEqual(PortalAccountBooking.objects.filter(account=original).count(), 1)
        self.assertEqual(RegistrationOrder.objects.count(), 101)
        self.assertEqual(Participant.objects.count(), 101)

    def test_other_email_existing_owner_and_wrong_password_boundaries(self):
        payload = deepcopy(self.order_payload)
        payload['primary_registrant']['email'] = 'other@example.test'
        payload['portal_account'].update(mode='existing', password='incorrect')
        denied = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(denied.status_code, 403)
        payload['portal_account']['password'] = self.order_payload['portal_account']['password']
        accepted = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(PortalAccountBooking.objects.values('account_id').distinct().count(), 1)

    def test_payment_initialization_reuses_receipt_email_and_idempotency(self):
        with patch('dic.payment_views.PaystackClient') as factory:
            factory.return_value.initialize_transaction.side_effect = lambda **kw: {'authorization_url': 'https://checkout.paystack.com/synthetic', 'reference': kw['reference']}
            url = reverse('dic:payment-initialize', args=[self.order.public_id])
            for _ in range(2):
                response = self.client.post(url, {}, format='json', **self.auth)
                self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(factory.return_value.initialize_transaction.call_count, 1)
            self.assertEqual(factory.return_value.initialize_transaction.call_args.kwargs['email'], self.order.primary_registrant.email)

    def test_restart_requires_original_credentials_and_refuses_any_attempt(self):
        url = reverse('dic:registration-restart-check', args=[self.order.public_id])
        credentials = {'identifier': self.order_payload['portal_account']['username'], 'password': 'wrong'}
        self.assertEqual(self.client.post(url, credentials, format='json').status_code, 403)
        credentials['password'] = self.order_payload['portal_account']['password']
        response = self.client.post(url, credentials, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertIsNotNone(self.order.access_token_revoked_at)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.order.pk).exists())

    def test_restart_does_not_cancel_unresolved_payment(self):
        fixtures.PaymentApiTests.create_pending_attempt(self)
        credentials = {'identifier': self.order_payload['portal_account']['username'], 'password': self.order_payload['portal_account']['password']}
        response = self.client.post(reverse('dic:registration-restart-check', args=[self.order.public_id]), credentials, format='json')
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertEqual(self.order.payment_attempts.count(), 1)


class DisposableRegistrationTests(TestCase):
    setUp = operations.DICOperationsTests.setUp
    make_order = operations.DICOperationsTests.make_order
    permission = operations.DICOperationsTests.permission
    make_staff = operations.DICOperationsTests.make_staff

    def manager(self):
        user = get_user_model().objects.create_superuser('synthetic-deleter', 'staff@example.test', 'synthetic-only')
        self.client.force_login(user)
        return user

    def delete(self, order, **data):
        return self.client.post(reverse('dic:operations-registration-delete', args=[order.public_id]),
            {'confirmation': str(order.public_id), 'reason': 'Owner selected disposable synthetic test', **data}, content_type='application/json')

    def test_explicit_delete_removes_only_order_and_retains_accounts_participants_audit(self):
        self.manager()
        enrollment = ensure_enrollment(self.unpaid_order.items.get().pk)
        participant = enrollment.participant
        detail = self.client.get(reverse('dic:operations-registration-detail', args=[self.unpaid_order.public_id]))
        self.assertTrue(detail.json()['deletion']['eligible'])
        self.assertEqual(self.delete(self.unpaid_order, confirmation='wrong').status_code, 400)
        self.assertEqual(self.delete(self.unpaid_order).status_code, 200)
        self.assertFalse(RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).exists())
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.paid_order.pk).exists())
        self.assertTrue(Participant.objects.filter(pk=participant.pk).exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='registration_test_deleted', target_id=str(self.unpaid_order.pk)).exists())
        self.assertEqual(self.delete(self.unpaid_order).status_code, 404)

    def test_unauthorized_paid_and_payment_attempts_fail_closed(self):
        self.assertIn(self.delete(self.unpaid_order).status_code, (401, 403))
        self.manager()
        self.assertEqual(self.delete(self.paid_order).status_code, 400)
        from .models import PaymentAttempt
        PaymentAttempt.objects.create(order=self.unpaid_order, reference='synthetic-pending', amount_kobo=10000, status='pending')
        self.assertEqual(self.delete(self.unpaid_order).status_code, 400)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).exists())

    def test_checkin_and_issued_dependencies_are_never_removed(self):
        from .registration_cleanup import disposal_blocker
        manager = self.manager()
        participant = self.unpaid_order.items.get().participant
        checkin = CampCheckIn.objects.create(participant=participant, edition=self.edition, checked_in_by=manager)
        self.assertIn('Check-in', disposal_blocker(self.unpaid_order))
        self.assertEqual(self.delete(self.unpaid_order).status_code, 400)
        self.assertTrue(CampCheckIn.objects.filter(pk=checkin.pk).exists())

    def test_record_view_permission_without_delete_permission_cannot_delete(self):
        from django.test import Client
        user = get_user_model().objects.create_user('viewer-only', password='synthetic', is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='dic', codename__in=(
            'can_view_dic_operations', 'view_registrationorder', 'can_manage_registration_access')))
        self.client.force_login(user)
        self.assertEqual(self.delete(self.unpaid_order).status_code, 403)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).exists())
        admin = self.manager()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(admin)
        response = browser.post(reverse('dic:operations-registration-delete', args=[self.unpaid_order.public_id]),
            {'confirmation': str(self.unpaid_order.public_id), 'reason': 'Synthetic'}, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_issued_id_evidence_protects_even_inconsistent_unpaid_legacy_record(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import DigitalIDIssue
        manager = self.manager()
        enrollment = ensure_enrollment(self.unpaid_order.items.get().pk)
        # Deliberately inconsistent synthetic legacy evidence. Never an issuance path.
        DigitalIDIssue.objects.bulk_create([DigitalIDIssue(enrollment=enrollment, version=1,
            issued_by=manager, expires_at=timezone.now()+timedelta(days=1))])
        self.assertEqual(self.delete(self.unpaid_order).status_code, 400)
        self.assertEqual(DigitalIDIssue.objects.filter(enrollment=enrollment).count(), 1)
        self.assertTrue(CampEnrollment.objects.filter(pk=enrollment.pk).exists())


class AuthorizedDependentIDTests(PortalFixtures, TestCase):
    issue = identity.IdentityCardTests.issue
    portal_client = identity.IdentityCardTests.portal_client
    portal_card_url = identity.IdentityCardTests.portal_card_url

    def setUp(self):
        super().setUp()
        self.enrollment = ensure_enrollment(self.item.pk)

    def test_issued_child_id_opens_without_guardian_while_scope_and_issuance_are_enforced(self):
        self.enrollment.participant.date_of_birth = date(2022, 1, 1)
        self.enrollment.participant.save()
        browser, _ = self.portal_client()
        self.assertContains(browser.get(self.portal_card_url()), 'no active eligible ID is available')
        self.assertNotContains(browser.get(self.portal_card_url()), 'data:image/svg+xml;base64,')
        self.issue()
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 200)
        self.assertEqual(self.client.get(self.portal_card_url()).status_code, 403)
        other = ensure_enrollment(self.unpaid_order.items.first().pk)
        self.assertEqual(browser.get(self.portal_card_url(other)).status_code, 404)


    @override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True)
    def test_accounts_sharing_receipt_email_have_disjoint_paid_portal_scope(self):
        from .models import PortalAccount
        from .recovery_views import _contact_digest
        from rest_framework.test import APIClient
        self.issue()
        other = self.make_order(('Other camper',), paid=True)
        other.primary_registrant.email = self.paid_order.primary_registrant.email
        other.primary_registrant.save(update_fields=['email'])
        foreign = ensure_enrollment(other.items.get().pk)
        for index, order in enumerate((self.paid_order, other)):
            user = get_user_model().objects.create_user(username=f'scope-owner-{index}', password='synthetic-only')
            account = PortalAccount.objects.create(user=user, username_key=user.username, contact_channel='identity', contact_digest=_contact_digest('identity', user.username))
            PortalAccountBooking.objects.create(account=account, order=order)
            browser = APIClient()
            response = browser.post(reverse('dic:portal-password-login'), {'identifier': user.username, 'password': 'synthetic-only'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            rows = browser.get(reverse('dic:participant-enrollments')).data['orders']
            self.assertEqual([row['reference'] for row in rows], [str(order.public_id)])
            denied = foreign if index == 0 else self.enrollment
            self.assertEqual(browser.get(self.portal_card_url(denied)).status_code, 404)


from django.test import TransactionTestCase

class DisposableConcurrencyTests(TransactionTestCase):
    setUp = operations.DICOperationsTests.setUp
    make_order = operations.DICOperationsTests.make_order

    def worker(self, operation):
        from django.db import close_old_connections, connection
        close_old_connections()
        try:
            return operation()
        finally:
            connection.close()

    def test_two_delete_requests_remove_one_order_and_write_one_audit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from .registration_cleanup import delete_disposable_registration
        actor = get_user_model().objects.create_superuser('race-deleter', 'race@example.test', 'synthetic-only')
        reference, ready = self.unpaid_order.public_id, Barrier(2)
        def remove():
            ready.wait(timeout=5)
            try:
                delete_disposable_registration(reference, actor, str(reference), 'Explicit synthetic concurrent deletion')
                return 'deleted'
            except RegistrationOrder.DoesNotExist:
                return 'missing'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.worker(remove), range(2)))
        self.assertEqual(sorted(results), ['deleted', 'missing'])
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='registration_test_deleted').count(), 1)
        self.assertTrue(RegistrationOrder.objects.filter(pk=self.paid_order.pk).exists())

    def test_payment_evidence_committed_under_order_lock_blocks_waiting_delete(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import transaction
        from rest_framework.exceptions import ValidationError
        from .models import PaymentAttempt
        from .registration_cleanup import delete_disposable_registration
        actor = get_user_model().objects.create_superuser('payment-race-deleter', 'race@example.test', 'synthetic-only')
        reference = self.unpaid_order.public_id
        locked, release = Event(), Event()
        def initialize():
            with transaction.atomic():
                order = RegistrationOrder.objects.select_for_update().get(public_id=reference)
                PaymentAttempt.objects.create(order=order, reference='locked-synthetic-init', amount_kobo=10000, status='pending')
                locked.set()
                if not release.wait(timeout=10): raise AssertionError('Synthetic release timeout')
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(self.worker, initialize)
            self.assertTrue(locked.wait(timeout=5))
            deletion = pool.submit(self.worker, lambda: delete_disposable_registration(reference, actor, str(reference), 'Synthetic race'))
            release.set(); pending.result(timeout=15)
            with self.assertRaises(ValidationError): deletion.result(timeout=15)
        self.assertTrue(RegistrationOrder.objects.filter(public_id=reference).exists())
        self.assertTrue(PaymentAttempt.objects.filter(reference='locked-synthetic-init').exists())
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='registration_test_deleted').exists())
