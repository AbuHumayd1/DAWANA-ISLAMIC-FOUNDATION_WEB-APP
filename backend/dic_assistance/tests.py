"""No real provider, delivery or database access in these policy checks."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate
from dic.assisted_registration import AssistedBookingCreateView
from .services import require_assistance, receipt


class AssistancePolicyTests(SimpleTestCase):
    def actor(self, **changes):
        return SimpleNamespace(**{**dict(pk=1, is_authenticated=True, is_active=True, is_staff=True, is_superuser=False,
            has_perm=lambda p: p in ('dic.can_view_dic_operations', 'dic_assistance.can_assist_registration')), **changes})

    def test_creation_permission_is_independent(self):
        require_assistance(self.actor())
        for changes in [dict(is_active=False), dict(is_staff=False), dict(is_authenticated=False),
                        dict(has_perm=lambda p: p == 'dic.can_view_dic_operations'),
                        dict(has_perm=lambda p: p == 'dic_assistance.can_assist_registration')]:
            with self.assertRaises(PermissionDenied): require_assistance(self.actor(**changes))

    def test_denial_occurs_before_database_or_creation(self):
        for actor in [None, self.actor(has_perm=lambda _: False)]:
            request = APIRequestFactory().post('/create/', {}, format='json')
            if actor: force_authenticate(request, actor)
            with patch('dic_assistance.services.create_assistance') as create:
                response = AssistedBookingCreateView.as_view()(request)
            self.assertEqual(response.status_code, 403); create.assert_not_called()

    def test_receipt_never_exposes_payer_capability_or_private_status(self):
        from django.utils import timezone
        value = receipt(SimpleNamespace(pk=uuid4(), created_at=timezone.now()), False)
        self.assertEqual(set(value), {'assistance_id', 'created_at', 'registration_created', 'payment_started',
                                      'idempotent_replay', 'recovery_path', 'message'})
        self.assertFalse(value['payment_started'])

    def test_creation_input_rejects_missing_request_id_and_payment_override(self):
        from dic.assisted_registration import AssistedCreationInput
        self.assertFalse(AssistedCreationInput(data={}).is_valid())
        self.assertFalse(AssistedCreationInput(data={'request_id': str(uuid4()), 'payment_status': 'paid'}).is_valid())

    def test_disabled_creation_fails_closed_without_storage(self):
        from django.test import override_settings
        request = APIRequestFactory().post('/create/', {}, format='json')
        force_authenticate(request, self.actor())
        with override_settings(DIC_ASSISTED_BOOKING_ENABLED=False), patch('dic_assistance.services.create_assistance') as create:
            response = AssistedBookingCreateView.as_view()(request)
        self.assertEqual(response.status_code, 503); create.assert_not_called()

    def test_authorized_api_uses_server_actor_and_no_payer_token(self):
        from django.test import override_settings
        from dic.test_assisted_preparation import AssistedPreparationTests
        actor = self.actor(); payload = AssistedPreparationTests().payload()
        payload['request_id'] = str(uuid4())
        request = APIRequestFactory().post('/create/', payload, format='json')
        force_authenticate(request, actor)
        with override_settings(DIC_ASSISTED_BOOKING_ENABLED=True), patch('dic.recovery.channel_available', return_value=True), patch(
                'dic_assistance.services.create_assistance', return_value={'idempotent_replay': False}) as create:
            response = AssistedBookingCreateView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertIs(create.call_args.args[0], actor)
        self.assertIn('no-store', response['Cache-Control'])
