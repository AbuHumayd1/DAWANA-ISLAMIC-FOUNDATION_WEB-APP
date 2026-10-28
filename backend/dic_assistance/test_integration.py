"""Explicit disposable PostgreSQL only, no live payments or outbound delivery."""
import re
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from dic.assisted_registration import AssistedPreparationInput
from dic.models import CampEdition, RegistrationCategory, RegistrationOrder, CampEnrollment, PaymentAttempt, DigitalIDIssue
from dic.participant_services import eligibility
from dic.views import _create_order, _request_fingerprint, IdempotencyConflict
from .services import create_assistance
from .models import RegistrationAssistance


class AssistanceIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_assistance_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Disposable assistance PostgreSQL required.')
        super().setUpClass()

    def setUp(self):
        self.actor = get_user_model().objects.create_user(username='synthetic-assistant', is_staff=True)
        self.actor.has_perm = lambda p: p in ('dic.can_view_dic_operations', 'dic_assistance.can_assist_registration')
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(name='SYNTHETIC Assistance', year=2097,
            camp_start_date=today + timedelta(days=60), camp_end_date=today + timedelta(days=65),
            registration_open_date=today - timedelta(days=1), registration_close_date=today + timedelta(days=1),
            registration_status='open', is_active=True)
        self.category = RegistrationCategory.objects.create(edition=self.edition, name='Synthetic category', fee_ngn=Decimal('12500.25'))
        raw = {'registration': {'primary_registrant': {'full_name': 'Synthetic payer', 'email': 'payer@example.test'},
            'participants': [dict(category_id=self.category.pk, full_name='Synthetic camper', address='Test', phone='08012345678',
                email='camper@example.test', date_of_birth='2000-01-01', sex='Male', height_cm='170.01', weight_kg='70.01',
                academic_status='Tertiary Student', occupation='None', marital_status='None')]}}
        serializer = AssistedPreparationInput(data=raw); serializer.is_valid(raise_exception=True)
        self.payload = serializer.validated_data['registration']
        self.channel = patch('dic.recovery.channel_available', return_value=True); self.channel.start(); self.addCleanup(self.channel.stop)

    def test_creation_audit_pricing_and_no_premature_eligibility(self):
        with patch('dic.payments.PaystackClient') as provider:
            result = create_assistance(self.actor, uuid4(), self.payload)
        row = RegistrationAssistance.objects.get()
        self.assertEqual(str(row.pk), result['assistance_id']); self.assertEqual(row.actor, self.actor)
        self.assertEqual(row.edition, self.edition); self.assertEqual(row.order.total_amount_ngn, Decimal('12500.25'))
        self.assertFalse(eligibility(CampEnrollment.objects.get())['eligible'])
        self.assertFalse(PaymentAttempt.objects.exists()); self.assertFalse(DigitalIDIssue.objects.exists())
        self.assertLessEqual(row.order.access_token_expires_at, timezone.now()); provider.assert_not_called()
        from rest_framework.test import APIClient
        from django.urls import reverse
        self.assertEqual(APIClient().get(reverse('dic:order-detail', args=[row.order.public_id])).status_code, 404)

    def test_replay_preserves_payer_recovered_token_and_actor_ownership(self):
        key = uuid4(); first = create_assistance(self.actor, key, self.payload)
        order = RegistrationAssistance.objects.get().order
        RegistrationOrder.objects.filter(pk=order.pk).update(access_token_digest='payer-recovered-digest')
        again = create_assistance(self.actor, key, self.payload)
        order.refresh_from_db(); self.assertEqual(order.access_token_digest, 'payer-recovered-digest')
        self.assertEqual(first['assistance_id'], again['assistance_id']); self.assertTrue(again['idempotent_replay'])
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        other = get_user_model().objects.create_user(username='other', is_staff=True)
        other.has_perm = self.actor.has_perm
        with self.assertRaises(IdempotencyConflict): create_assistance(other, key, self.payload)
        changed = deepcopy(self.payload); changed['primary_registrant']['full_name'] = 'Changed'
        with self.assertRaises(IdempotencyConflict): create_assistance(self.actor, key, changed)

    def test_new_key_existing_camper_is_review_not_takeover(self):
        create_assistance(self.actor, uuid4(), self.payload)
        with self.assertRaises(ValidationError): create_assistance(self.actor, uuid4(), self.payload)
        self.assertEqual(RegistrationOrder.objects.count(), 1)

    def test_multicamper_and_existing_public_service_compatibility(self):
        second = deepcopy(self.payload['participants'][0]); second['full_name'] = 'Second synthetic camper'
        self.payload['participants'].append(second)
        create_assistance(self.actor, uuid4(), self.payload)
        self.assertEqual(CampEnrollment.objects.count(), 2)
        self.assertEqual(RegistrationAssistance.objects.get().order.total_amount_ngn, Decimal('25000.50'))
        public, token, replayed = _create_order(key_digest='synthetic-public-key', fingerprint=_request_fingerprint(self.payload), payload=self.payload)
        self.assertTrue(token); self.assertFalse(replayed); self.assertEqual(public.items.count(), 2)

    def test_validation_permission_and_channel_failure_are_atomic(self):
        self.actor.has_perm = lambda _: False
        with self.assertRaises(PermissionDenied): create_assistance(self.actor, uuid4(), self.payload)
        self.actor.has_perm = lambda _: True
        with patch('dic.recovery.channel_available', return_value=False), self.assertRaises(ValidationError):
            create_assistance(self.actor, uuid4(), self.payload)
        self.payload['participants'][0]['category_id'] = 999999
        with self.assertRaises(ValidationError): create_assistance(self.actor, uuid4(), self.payload)
        self.assertFalse(RegistrationOrder.objects.exists()); self.assertFalse(RegistrationAssistance.objects.exists())


# Exercise the existing OTP/restore boundary against assisted orders, without
# importing the full recovery suite into this test manifest or using test flush.
from django.test import override_settings
from dic.test_recovery import RegistrationRecoveryTests as RecoveryCases


@override_settings(**RecoveryCases._overridden_settings)
class AssistedRecoveryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_assistance_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Disposable assistance PostgreSQL required.')
        super().setUpClass()
    setUp = RecoveryCases.setUp
    participant = RecoveryCases.participant
    start = RecoveryCases.start
    verify = RecoveryCases.verify
    read_code = RecoveryCases.read_code
    process_deliveries = RecoveryCases.process_deliveries
    _resend_after_cooldown = RecoveryCases._resend_after_cooldown
    test_contact_verification_and_single_use_restore = RecoveryCases.test_email_recovery_scopes_order_and_rotates_access_token
    test_wrong_expired_and_reused_otp = RecoveryCases.test_wrong_expired_and_reused_codes_are_rejected
    test_expired_grant_and_no_grant = RecoveryCases.test_grants_expire_and_are_required_for_order_retrieval

    def create_order(self, *, email='participant@example.test', phone='+2348012345678', name='Test Participant'):
        actor = get_user_model().objects.create_user(username='synthetic-recovery-assistant', is_staff=True)
        actor.has_perm = lambda _: True
        serializer = AssistedPreparationInput(data={'registration': {
            'primary_registrant': {'full_name': 'Synthetic payer', 'email': email, 'phone': phone},
            'participants': [self.participant(name=name, email=email, phone=phone)]}})
        serializer.is_valid(raise_exception=True)
        create_assistance(actor, uuid4(), serializer.validated_data['registration'])
        return RegistrationOrder.objects.get(), 'never-issued-to-officer'


class AssistanceConcurrencyTests(SimpleTestCase):
    """Last probe: committed synthetic rows retained in disposable DB; no flush."""
    databases = {'default'}

    def test_concurrent_same_and_new_request_keys_create_one_order(self):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_assistance_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Disposable assistance PostgreSQL required.')
        AssistanceIntegrationTests.setUp(self)
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections, connections
        key = uuid4()
        def run(request):
            close_old_connections()
            try: return create_assistance(self.actor, request, self.payload)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [key, key]))
        self.assertEqual(results[0]['assistance_id'], results[1]['assistance_id'])
        self.assertEqual(sorted(row['idempotent_replay'] for row in results), [False, True])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, uuid4()) for _ in range(2)]
            for future in futures:
                with self.assertRaises(ValidationError): future.result()
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertEqual(RegistrationAssistance.objects.count(), 1)
