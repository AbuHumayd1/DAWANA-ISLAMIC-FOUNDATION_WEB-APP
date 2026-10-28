"""Field preparation only; database/network effects must remain impossible."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from .assisted_registration import AssistedRegistrationPreparationView, validate_preparation
from .assisted_registration import AssistedOrderInput as RegistrationOrderCreateSerializer


class AssistedPreparationTests(SimpleTestCase):
    def payload(self):
        return {'registration': {'primary_registrant': {'full_name': 'Synthetic payer', 'email': 'payer@example.test', 'phone': ''},
            'participants': [dict(category_id=1, full_name='Synthetic camper', address='Synthetic address', phone='08012345678',
                email='camper@example.test', date_of_birth='2000-01-01', sex='Male', height_cm='170.01', weight_kg='70.01',
                academic_status='Tertiary Student', occupation='None', marital_status='None')]}}

    def actor(self, **changes):
        return SimpleNamespace(**{**dict(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False,
            has_perm=lambda permission: permission == 'dic.can_view_dic_operations'), **changes})

    def request(self, actor, method='post', data=None):
        request = getattr(APIRequestFactory(), method)('/api/v1/dic/operations/assisted-registration/', data if data is not None else self.payload(), format='json')
        if actor: force_authenticate(request, user=actor)
        return AssistedRegistrationPreparationView.as_view()(request)

    def test_existing_registration_schema_is_reused_without_mutating_payload(self):
        payload = self.payload(); before = deepcopy(payload)
        serializer = RegistrationOrderCreateSerializer(data=payload['registration'])
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(validate_preparation(payload)['fields_valid'])
        self.assertEqual(payload, before)

    def test_all_current_camper_fields_including_dob_remain_required(self):
        for key in self.payload()['registration']['participants'][0]:
            if key in ('height_cm', 'weight_kg'):
                continue  # Optional measurements now use the shared public schema.
            payload = self.payload(); del payload['registration']['participants'][0][key]
            with self.subTest(key=key), self.assertRaises(ValidationError): validate_preparation(payload)

    def test_future_dob_still_rejected(self):
        payload = self.payload(); payload['registration']['participants'][0]['date_of_birth'] = '2999-01-01'
        with self.assertRaises(ValidationError): validate_preparation(payload)

    def test_payment_role_fee_and_actor_override_fields_rejected(self):
        for field in ['payment_status', 'amount_kobo', 'actor', 'exempt', 'is_staff', 'access_token']:
            for location in ['root', 'registration', 'participant']:
                payload = self.payload()
                target = payload if location == 'root' else payload['registration'] if location == 'registration' else payload['registration']['participants'][0]
                target[field] = 'synthetic'
                with self.subTest(field=field, location=location), self.assertRaises(ValidationError): validate_preparation(payload)

    def test_payer_name_and_recoverable_contact_required(self):
        for payer in [{}, {'full_name': 'Synthetic payer'}, {'email': 'payer@example.test'}]:
            payload = self.payload(); payload['registration']['primary_registrant'] = payer
            with self.assertRaises(ValidationError): validate_preparation(payload)

    def test_bad_recovery_phone_rejected(self):
        payload = self.payload(); payload['registration']['primary_registrant']['phone'] = 'not-a-phone'
        with self.assertRaises(ValidationError): validate_preparation(payload)

    def test_anonymous_inactive_nonstaff_and_nonoperations_rejected_before_validation(self):
        for actor in [None, self.actor(is_active=False), self.actor(is_staff=False), self.actor(has_perm=lambda _: False)]:
            for method in ['get', 'post']:
                with patch('dic.assisted_registration.validate_preparation') as validate:
                    self.assertEqual(self.request(actor, method).status_code, 403)
                    validate.assert_not_called()

    def test_metadata_explicitly_disables_creation(self):
        response = self.request(self.actor(), 'get')
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data['creation_enabled'], False)
        self.assertEqual(response.data['recovery_path'], '/dic/register/recover')
        self.assertIn('no-store', response['Cache-Control'])

    @patch('dic.views._create_order')
    @patch('dic.payments.PaystackClient')
    @patch('dic.participant_services.eligibility')
    def test_repeated_field_checks_cannot_create_pay_fulfill_or_activate(self, eligibility, paystack, create):
        for _ in range(3):
            response = self.request(self.actor())
            self.assertEqual(response.status_code, 200)
            self.assertIs(response.data['registration_created'], False)
            self.assertIs(response.data['payment_started'], False)
            self.assertNotIn('access_token', response.data)
            self.assertNotIn('participant', response.data)
        create.assert_not_called(); paystack.assert_not_called(); eligibility.assert_not_called()

    def test_malformed_empty_or_create_action_request_rejected(self):
        for data in [[], {}, {'action': 'create', **self.payload()}, {'registration': {'participants': []}}]:
            with self.assertRaises(ValidationError): validate_preparation(data)
