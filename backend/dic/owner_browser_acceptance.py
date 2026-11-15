"""Explicit local browser check; synthetic test database, never production.

Run this module explicitly with DIC_OWNER_BROWSER_CHECK=1 and the frontend
test server on 127.0.0.1:5178. It is not part of browser-free core CI discovery.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import uuid
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from . import tests as fixtures
from .models import DICAdminAuditEvent, PaymentAttempt, RegistrationOrder
from .registration_cleanup import is_deleted, archived_test_orders


@skipUnless(os.environ.get('DIC_OWNER_BROWSER_CHECK') == '1', 'Explicit local browser acceptance only')
@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock',
                   CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:5178'])
class OwnerBrowserAcceptance(LiveServerTestCase):
    host = '127.0.0.1'
    client_class = APIClient
    setUp = fixtures.PaymentApiTests.setUp

    def test_real_frontend_and_backend_delete_restore_archive_unarchive(self):
        records = []
        for index, state in enumerate(('pending', 'failed', 'amount_mismatch', 'init_unknown', 'paid')):
            if index == 0:
                order = self.order
            else:
                payload = deepcopy(self.order_payload)
                payload['portal_account']['username'] = 'browser-camper-'+str(index)
                response = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                self.assertEqual(response.status_code, 201, response.data)
                order = RegistrationOrder.objects.get(public_id=response.data['order_id'])
            PaymentAttempt.objects.create(order=order, reference='browser-synthetic-'+str(index),
                amount_kobo=int(order.total_amount_ngn * 100),
                price_revision=order.current_price_revision, status='successful' if state == 'paid' else state)
            if state == 'paid':
                order.payment_status = 'paid'; order.status = 'confirmed'
                order.save(update_fields=['payment_status', 'status'])
            records.append({'id': str(order.public_id), 'state': state})
        admin = get_user_model().objects.create_superuser('browser-owner', 'owner@example.test', 'synthetic-only')
        self.client.force_login(admin)
        env = {**os.environ, 'OWNER_TEST_API': self.live_server_url,
               'OWNER_TEST_SESSION': self.client.cookies['sessionid'].value,
               'OWNER_TEST_RECORDS': json.dumps(records)}
        frontend = Path(__file__).resolve().parents[2] / 'dawana-platform'
        result = subprocess.run(['node', 'scripts/check-owner-backend.cjs'], cwd=frontend, env=env,
                                text=True, capture_output=True, timeout=180)
        print(result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        for record in records:
            order = RegistrationOrder.objects.get(public_id=record['id'])
            self.assertFalse(is_deleted(order))
            self.assertFalse(archived_test_orders().filter(pk=order.pk).exists())
            self.assertEqual(order.payment_attempts.count(), 1)
            expected = 'paid' if record['state'] == 'paid' else 'pending'
            self.assertEqual(order.payment_status, expected)
            for action in ('registration_trashed', 'registration_restored', 'registration_test_archived', 'registration_unarchived'):
                events = DICAdminAuditEvent.objects.filter(action=action, target_id=str(order.pk))
                self.assertEqual(events.count(), 2, (record['state'], action))
                for event in events:
                    self.assertEqual(event.actor_id, admin.pk)
                    self.assertEqual(event.details['reference'], record['id'])
                    self.assertIsNotNone(event.created_at)
