"""Reproduce hidden order validation errors without database or provider access."""
from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from .views import RegistrationOrderCreateView


class CheckoutValidationTests(SimpleTestCase):
    def payload(self):
        return {
            'portal_account': {'username': 'synthetic-camper', 'password': 'River-Cedar!Sparrow-84',
                               'password_confirmation': 'River-Cedar!Sparrow-84'},
            'primary_registrant': {'full_name': 'Synthetic Guardian', 'email': 'guardian@example.test'},
            'participants': [{'category_id': 1, 'full_name': 'Synthetic Participant',
                'address': 'Synthetic address', 'phone': '+2348000000000', 'email': 'camper@example.test',
                'date_of_birth': '2000-01-01', 'sex': 'Male', 'academic_status': 'Tertiary Student',
                'occupation': 'None', 'marital_status': 'Single'}],
        }

    def rejected(self, payload):
        with patch('dic.views._create_order') as create, \
                patch('dic.portal_accounts.rate_limit') as rate_limit, \
                patch('dic.payment_views.PaystackClient') as provider:
            response = RegistrationOrderCreateView.as_view()(APIRequestFactory().post(
                '/api/v1/dic/orders/', payload, format='json',
                HTTP_IDEMPOTENCY_KEY='4113e835-cd19-43b5-bec4-29e11c710328'))
        self.assertEqual(response.status_code, 400)
        create.assert_not_called()
        rate_limit.assert_not_called()
        provider.assert_not_called()
        return response.data

    def test_numeric_password_returns_nested_account_error_before_order_or_payment_creation(self):
        payload = self.payload()
        payload['portal_account'].update(password='123456789012', password_confirmation='123456789012')
        errors = self.rejected(payload)
        self.assertIn('portal_account', errors)
        self.assertIn('entirely numeric', str(errors['portal_account']))
        self.assertNotIn('123456789012', str(errors))

    def test_invalid_second_participant_email_retains_index_without_echoing_contact(self):
        payload = self.payload()
        payload['participants'].append(deepcopy(payload['participants'][0]))
        payload['participants'][1]['email'] = 'private-invalid-contact'
        errors = self.rejected(payload)
        rows = errors['participants']
        # DRF returns a positional list or a sparse index map, by version.
        if isinstance(rows, list):
            self.assertEqual(rows[0], {})
        else:
            self.assertNotIn(0, rows)
        self.assertIn('email', rows[1])
        self.assertNotIn('private-invalid-contact', str(errors))
