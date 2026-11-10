"""Username cutover integration; run only through the existing isolated DB guards."""
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient, APITransactionTestCase
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from . import tests as fixtures
from . import portal_accounts as accounts
from .credential_transition import issue, consume
from .models import (PortalAccount, PortalAccountBooking, PortalCredentialTransition,
    ParticipantPortalGrant, DICAdminAuditEvent, RegistrationOrder)

PASSWORD = 'River-Cedar!Sparrow-84'
NEW_PASSWORD = 'Lantern-Copper!River-93'


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, DEBUG=False,
    EMAIL_BACKEND='config.https_email.EmailBackend', RESEND_API_KEY='', DEFAULT_FROM_EMAIL='',
    PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class UsernameAuthenticationTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def account(self):
        return PortalAccountBooking.objects.select_related('account__user').get(order=self.order).account

    def login(self, client=None, username='synthetic-registrant', password=PASSWORD):
        client = client or self.client
        csrf = client.get(reverse('dic:participant-csrf')).json()['csrfToken']
        return client.post(reverse('dic:portal-password-login'), {'identifier': username, 'password': password},
            format='json', HTTP_X_CSRFTOKEN=csrf)

    def settle(self):
        from .payment_views import _apply_verified_transaction
        attempt = self.create_pending_attempt()
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))

    def owner(self):
        return get_user_model().objects.create_superuser(username='recovery-owner', password=NEW_PASSWORD)

    def test_unpaid_account_authenticates_but_cannot_issue_portal_session(self):
        self.assertEqual(accounts.password_account(' SYNTHETIC-REGISTRANT ', PASSWORD).pk, self.account().pk)
        response = self.login()
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(ParticipantPortalGrant.objects.exists())

    def test_paid_login_logout_scope_and_refund_revocation_without_email(self):
        self.settle()
        self.client = APIClient(enforce_csrf_checks=True)
        response = self.login(username=' SYNTHETIC-REGISTRANT ')
        self.assertEqual(response.status_code, 200, response.data)
        orders = self.client.get(reverse('dic:participant-enrollments')).data['orders']
        self.assertEqual([row['reference'] for row in orders], [str(self.order.public_id)])
        self.assertEqual(len(orders[0]['participants']), self.order.items.count())
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.get(reverse('dic:operations-me')).status_code, 403)
        RegistrationOrder.objects.filter(pk=self.order.pk).update(payment_status='refunded')
        self.assertEqual(self.client.get(reverse('dic:participant-me')).status_code, 403)
        csrf = self.client.get(reverse('dic:participant-csrf')).json()['csrfToken']
        self.assertEqual(self.client.post(reverse('dic:participant-logout'), {}, HTTP_X_CSRFTOKEN=csrf).status_code, 204)
        self.assertEqual(self.client.get(reverse('dic:participant-me')).status_code, 403)

    def test_login_and_transition_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        for route, body in (('portal-password-login', {'identifier': 'synthetic-registrant', 'password': PASSWORD}),
                            ('portal-credential-transition', {'token': 'x'*43})):
            self.assertEqual(client.post(reverse('dic:'+route), body, format='json').status_code, 403)

    def test_login_has_generic_failure_and_real_rate_limits(self):
        for identifier in ('absent-user', 'synthetic-registrant'):
            responses = [self.login(username=identifier, password='incorrect') for _ in range(11)]
            self.assertTrue(all(r.status_code == 403 for r in responses[:10]))
            self.assertEqual(responses[-1].status_code, 429)
            self.assertEqual(responses[0].data['detail'], accounts.INVALID)

    def test_case_insensitive_username_uniqueness_is_database_enforced(self):
        other = get_user_model().objects.create_user(username='second-record')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PortalAccount.objects.create(user=other, username_key='SYNTHETIC-REGISTRANT',
                contact_channel='username', contact_digest='different-contact')

    def test_username_contact_snapshot_is_rechecked_without_becoming_email_proof(self):
        from .participant_api import primary_contact_matches
        account = self.account()
        self.assertTrue(primary_contact_matches(self.order, account.contact_channel, account.contact_digest))
        self.order.primary_registrant.email = 'changed@example.test'
        self.assertFalse(primary_contact_matches(self.order, account.contact_channel, account.contact_digest))

    def test_new_username_activation_is_not_email_proof(self):
        account = self.account()
        self.assertTrue(account.user.is_active)
        self.assertEqual(account.contact_channel, 'username')
        self.assertIsNone(account.login_email)
        self.assertFalse(DICAdminAuditEvent.objects.filter(target_type='PortalAccount', target_id=str(account.pk),
            action='portal_account_email_verified').exists())

    def test_optional_fresh_email_proof_can_reset_linked_username_account(self):
        from types import SimpleNamespace
        account = self.account()
        proof = SimpleNamespace(channel='email', contact_digest=account.contact_digest)
        with patch.object(accounts, 'fresh_otp', return_value=(proof, [self.order])):
            recovered = accounts.reset_password(object(), NEW_PASSWORD)
        self.assertEqual(recovered.pk, account.pk)
        self.assertEqual(recovered.contact_channel, 'username')
        self.assertIsNone(recovered.login_email)
        self.assertTrue(recovered.user.check_password(NEW_PASSWORD))
        self.assertEqual(recovered.credential_version, 2)
        self.assertFalse(ParticipantPortalGrant.objects.exists())

    def test_legacy_active_username_and_hash_remain_usable(self):
        account = self.account()
        account.contact_channel, account.login_email = 'email', self.order.primary_registrant.email
        account.save(update_fields=['contact_channel', 'login_email'])
        hashed = account.user.password
        self.assertEqual(accounts.password_account(account.username_key.upper(), PASSWORD).pk, account.pk)
        account.user.refresh_from_db()
        self.assertEqual(account.user.password, hashed)

    def test_pending_legacy_transition_keeps_records_and_never_verifies_email(self):
        account = self.account()
        account.contact_channel, account.login_email = 'email', self.order.primary_registrant.email
        account.save(update_fields=['contact_channel', 'login_email'])
        account.user.is_active = False
        account.user.save(update_fields=['is_active'])
        accounts.audit(account, 'registration_pending')
        before = (account.user_id, account.pk, self.order.pk, list(self.order.items.values_list('pk', flat=True)))
        with self.assertRaises(AuthenticationFailed): accounts.password_account(account.username_key, PASSWORD)
        token = issue(self.owner(), self.order.public_id, 'Reviewed ownership case 2026-01', NEW_PASSWORD)
        recovered = consume(token, 'Chosen-Username', NEW_PASSWORD)
        self.assertEqual(recovered.pk, account.pk)
        recovered.user.refresh_from_db()
        self.assertTrue(recovered.user.is_active)
        self.assertEqual(recovered.user.username, 'chosen-username')
        self.assertEqual(recovered.contact_channel, 'username')
        self.assertEqual(before, (recovered.user_id, recovered.pk, self.order.pk, list(self.order.items.values_list('pk', flat=True))))
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='portal_account_credential_transition', target_id=str(account.pk)).exists())
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='portal_account_email_verified', target_id=str(account.pk)).exists())
        self.assertFalse(ParticipantPortalGrant.objects.exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'pending')
        with self.assertRaises(ValidationError): consume(token, 'chosen-username', PASSWORD)

    def test_transition_expiry_reissue_and_credential_version_fail_closed(self):
        owner = self.owner()
        old = issue(owner, self.order.public_id, 'Review case old authority', NEW_PASSWORD)
        new = issue(owner, self.order.public_id, 'Review case fresh authority', NEW_PASSWORD)
        with self.assertRaises(ValidationError): consume(old, 'changed-user', NEW_PASSWORD)
        PortalCredentialTransition.objects.filter(token_digest=accounts.digest_value(new)).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError): consume(new, 'changed-user', NEW_PASSWORD)
        fresh = issue(owner, self.order.public_id, 'Review case version change', NEW_PASSWORD)
        account = self.account(); account.credential_version += 1; account.save(update_fields=['credential_version'])
        with self.assertRaises(ValidationError): consume(fresh, 'changed-user', NEW_PASSWORD)
        self.assertEqual(self.account().username_key, 'synthetic-registrant')

    def test_admin_password_change_invalidates_outstanding_recovery_authority(self):
        token = issue(self.owner(), self.order.public_id, 'Review case admin password reset', NEW_PASSWORD)
        user = self.account().user
        user.set_password('Another-Cedar!Copper-92')
        user.save(update_fields=['password'])
        with self.assertRaises(ValidationError): consume(token, 'new-owner', NEW_PASSWORD)
        self.assertFalse(PortalCredentialTransition.objects.get().consumed_at)

    def test_revoked_issuer_cannot_leave_valid_recovery_authority(self):
        from rest_framework.exceptions import PermissionDenied
        owner = self.owner()
        token = issue(owner, self.order.public_id, 'Review case issuer revocation', NEW_PASSWORD)
        owner.is_superuser = False
        owner.save(update_fields=['is_superuser'])
        with self.assertRaises(PermissionDenied): consume(token, 'new-owner', NEW_PASSWORD)

    def test_reset_revokes_sessions_and_never_returns_a_session(self):
        self.settle()
        self.assertEqual(self.login().status_code, 200)
        token = issue(self.owner(), self.order.public_id, 'Reviewed lost credentials 2026', NEW_PASSWORD)
        consume(token, 'recovered-owner', NEW_PASSWORD)
        self.assertEqual(self.client.get(reverse('dic:participant-me')).status_code, 403)
        self.assertEqual(self.login(username='recovered-owner', password=NEW_PASSWORD).status_code, 200)

    def test_recovery_rejects_nonowners_wrong_reauthentication_and_privileged_targets(self):
        from rest_framework.exceptions import PermissionDenied
        ordinary = self.account().user
        with self.assertRaises(PermissionDenied): issue(ordinary, self.order.public_id, 'Review case unauthorized', PASSWORD)
        owner = self.owner()
        with self.assertRaises(PermissionDenied): issue(owner, self.order.public_id, 'Review case incorrect password', 'wrong')
        for field in ('is_staff', 'is_superuser'):
            target = self.account().user
            setattr(target, field, True); target.save(update_fields=[field])
            with self.assertRaises(PermissionDenied): issue(owner, self.order.public_id, 'Review case privileged account', NEW_PASSWORD)
            setattr(target, field, False); target.save(update_fields=[field])

    def test_existing_unbound_booking_is_claimed_without_replacing_records(self):
        from uuid import uuid4
        from .models import PrimaryRegistrant
        registrant = PrimaryRegistrant.objects.create(full_name='Legacy booking owner', email='legacy-unbound@example.test')
        order = RegistrationOrder.objects.create(edition=self.edition, primary_registrant=registrant,
            idempotency_key_digest=str(uuid4()), request_fingerprint='legacy-record', access_token_digest=str(uuid4()))
        token = issue(self.owner(), order.public_id, 'Reviewed old booking ownership', NEW_PASSWORD)
        account = consume(token, 'legacy-booking-owner', NEW_PASSWORD)
        binding = PortalAccountBooking.objects.get(order=order)
        self.assertEqual(binding.account_id, account.pk)
        self.assertEqual(binding.order.primary_registrant_id, registrant.pk)
        self.assertTrue(account.user.check_password(NEW_PASSWORD))
        self.assertFalse(account.user.is_staff)
        self.assertFalse(ParticipantPortalGrant.objects.exists())

    def test_recovery_issue_endpoint_requires_admin_session_csrf_and_reauthentication(self):
        route = reverse('dic:operations-account-recovery')
        body = {'order_reference': str(self.order.public_id), 'review_reference': 'Reviewed owner case 2026', 'password': NEW_PASSWORD}
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.account().user)
        csrf = client.get(reverse('dic:operations-csrf')).json()['csrfToken']
        self.assertEqual(client.post(route, body, format='json', HTTP_X_CSRFTOKEN=csrf).status_code, 403)
        client.force_login(self.owner())
        self.assertEqual(client.post(route, body, format='json').status_code, 403)
        csrf = client.get(reverse('dic:operations-csrf')).json()['csrfToken']
        wrong = client.post(route, {**body, 'password': 'incorrect'}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(wrong.status_code, 403)
        issued = client.post(route, body, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(issued.status_code, 200, issued.data)
        token = issued.data['token']
        self.assertEqual(len(token), 43)
        self.assertIn('no-store', issued['Cache-Control'])
        self.assertNotEqual(PortalCredentialTransition.objects.get().token_digest, token)
        self.assertTrue(all(token not in str(details) for details in DICAdminAuditEvent.objects.values_list('details', flat=True)))

    def test_suspended_account_cannot_be_reactivated_by_recovery(self):
        account = self.account(); account.user.is_active = False; account.user.save(update_fields=['is_active'])
        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied): issue(self.owner(), self.order.public_id, 'Review case suspended user', NEW_PASSWORD)


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True)
class UsernameConcurrencyTests(APITransactionTestCase):
    @classmethod
    def setUpClass(cls):
        import re
        from django.db import connection
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_core_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Fresh isolated core PostgreSQL required.')
        super().setUpClass()

    setUp = fixtures.PaymentApiTests.setUp

    def worker(self, operation):
        from django.db import close_old_connections, connection
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            return operation()
        finally:
            connection.close()

    def test_concurrent_case_variant_signup_creates_one_account_and_order(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from copy import deepcopy
        from uuid import uuid4
        ready = Barrier(2)
        payloads = []
        for index, username in enumerate(('Race-Owner', 'race-owner')):
            data = deepcopy(self.order_payload)
            data['portal_account']['username'] = username
            data['primary_registrant']['email'] = f'race-{index}@example.test'
            data['participants'][0]['full_name'] = f'Concurrent participant {index}'
            payloads.append(data)
        def register(data):
            ready.wait(timeout=5)
            return APIClient().post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, lambda data=data: register(data)) for data in payloads]
            statuses = sorted(f.result(timeout=20) for f in futures)
        self.assertEqual(statuses, [201, 403])
        self.assertEqual(PortalAccount.objects.filter(username_key='race-owner').count(), 1)
        self.assertEqual(RegistrationOrder.objects.count(), 2)  # Includes setup's original order.

    def test_concurrent_recovery_code_is_consumed_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        owner = get_user_model().objects.create_superuser(username='recovery-owner', password=NEW_PASSWORD)
        token = issue(owner, self.order.public_id, 'Reviewed concurrent recovery', NEW_PASSWORD)
        ready = Barrier(2)
        def reset():
            ready.wait(timeout=5)
            try:
                consume(token, 'recovered-concurrent', NEW_PASSWORD)
                return 'updated'
            except ValidationError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, reset) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=20) for f in futures), ['rejected', 'updated'])
        self.assertEqual(PortalAccountBooking.objects.get(order=self.order).account.credential_version, 2)
