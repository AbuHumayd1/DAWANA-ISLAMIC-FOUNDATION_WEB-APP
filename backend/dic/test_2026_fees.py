"""Approved payment schedule; all records in these tests are synthetic."""
from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import CampEdition, RegistrationCategory, Participant, RegistrationOrder, PaymentAttempt
from .pricing import price_for_category, PricingConfigurationError
from .registration_age import category_age_allowed
from .serializers import ParticipantInputSerializer
from .views import _create_order, _request_fingerprint

seed = import_module('dic.migrations.0034_approved_2026_fees').seed_approved_fees


class ApprovedFeesTests(TestCase):
    def setUp(self):
        seed(apps, SimpleNamespace(connection=connection))
        self.edition = CampEdition.objects.get(year=2026)
        self.today = timezone.localdate()
        self.edition.is_active = True
        self.edition.registration_status = 'open'
        self.edition.registration_open_date = self.today - timedelta(days=1)
        self.edition.registration_close_date = self.today + timedelta(days=1)
        self.edition.early_bird_cutoff_at = timezone.now() + timedelta(days=1)
        self.edition.save()
        self.categories = {c.payment_kind: c for c in self.edition.registration_categories.all()}

    def person(self, kind, age, status=None):
        raw = dict(category_id=self.categories[kind].pk, full_name='Synthetic Camper',
            address='Synthetic Address', phone='08012345678', email='synthetic@example.test',
            date_of_birth=date(self.today.year - age, self.today.month, self.today.day),
            sex='Female', academic_status=status or Participant.AcademicStatus.NOT_IN_SCHOOL,
            occupation='None', marital_status='None')
        serializer = ParticipantInputSerializer(data=raw)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def order(self, people):
        data = dict(primary_registrant={'full_name': 'Synthetic Guardian'}, participants=people)
        return _create_order(key_digest=str(uuid4()), fingerprint=_request_fingerprint(data), payload=data)

    def test_all_five_prices_before_and_at_cutoff(self):
        expected = {'pre_primary': (4000, 5000), 'primary': (10000, 12000),
            'secondary': (12000, 15000), 'undergraduate': (15000, 17000), 'graduate_adult': (18000, 18500)}
        for kind, (early, regular) in expected.items():
            category = self.categories[kind]
            with self.subTest(kind=kind):
                before = price_for_category(category, self.edition.early_bird_cutoff_at - timedelta(microseconds=1))
                after = price_for_category(category, self.edition.early_bird_cutoff_at)
                self.assertEqual((before['fee_ngn'], before['price_type']), (Decimal(early), 'early_bird'))
                self.assertEqual((after['fee_ngn'], after['price_type']), (Decimal(regular), 'regular'))

    def test_missing_deadline_is_not_invented(self):
        self.edition.early_bird_cutoff_at = None
        self.edition.save()
        seed(apps, SimpleNamespace(connection=connection))
        self.edition.refresh_from_db()
        self.assertIsNone(self.edition.early_bird_cutoff_at)
        with self.assertRaises(PricingConfigurationError):
            price_for_category(self.edition.registration_categories.first(), timezone.now())

    def test_age_boundaries_and_academic_eligibility(self):
        cases = [
            ('pre_primary', 0, None, True), ('pre_primary', 5, None, True), ('pre_primary', 6, None, False),
            ('primary', 5, None, False), ('primary', 6, None, True), ('primary', 10, None, True), ('primary', 11, None, False),
            ('secondary', 10, None, False), ('secondary', 11, None, True), ('secondary', 16, None, True), ('secondary', 17, None, False),
            ('undergraduate', 16, Participant.AcademicStatus.TERTIARY, False),
            ('undergraduate', 17, Participant.AcademicStatus.TERTIARY, True),
            ('undergraduate', 24, Participant.AcademicStatus.TERTIARY, True),
            ('undergraduate', 25, Participant.AcademicStatus.TERTIARY, False),
            ('undergraduate', 20, Participant.AcademicStatus.GRADUATE, False),
            ('undergraduate', 20, None, False),
            ('graduate_adult', 16, Participant.AcademicStatus.GRADUATE, True),
            ('secondary', 16, Participant.AcademicStatus.GRADUATE, False),
            ('graduate_adult', 16, None, False), ('graduate_adult', 17, None, True),
            ('graduate_adult', 18, None, True),
            ('graduate_adult', 24, None, True),
            ('graduate_adult', 24, Participant.AcademicStatus.TERTIARY, False),
            ('graduate_adult', 25, Participant.AcademicStatus.TERTIARY, True),
        ]
        for kind, age, status, expected in cases:
            with self.subTest(kind=kind, age=age, status=status):
                self.assertEqual(category_age_allowed(self.person(kind, age, status), self.categories[kind], self.today), expected)

    def test_private_adult_and_legacy_category_behaviour(self):
        data = dict(age_declaration='adult', date_of_birth=None, academic_status=Participant.AcademicStatus.NOT_IN_SCHOOL)
        self.assertTrue(category_age_allowed(data, self.categories['graduate_adult'], self.today))
        self.assertFalse(category_age_allowed(data, self.categories['undergraduate'], self.today))
        data['academic_status'] = Participant.AcademicStatus.TERTIARY
        self.assertFalse(category_age_allowed(data, self.categories['graduate_adult'], self.today))
        self.assertTrue(category_age_allowed(data, SimpleNamespace(minimum_age=18, maximum_age=None), self.today))

    def test_seventeen_year_old_payment_classification_preserves_minor_declaration(self):
        data = self.person('graduate_adult', 17)
        data['age_declaration'] = 'minor'
        self.assertTrue(category_age_allowed(data, self.categories['graduate_adult'], self.today))
        order, _, _ = self.order([data])
        participant = order.items.get().participant
        self.assertEqual(participant.age_declaration, 'minor')
        self.assertEqual(participant.date_of_birth, data['date_of_birth'])

    def test_admin_override_and_repeated_seed_preserve_fees(self):
        category = self.categories['primary']
        category.fee_ngn = Decimal('14000')
        category.early_bird_fee_ngn = Decimal('11000')
        category.is_active = False
        user = get_user_model().objects.create_superuser('fee-admin', 'admin@example.test', 'synthetic-password')
        request = RequestFactory().post('/admin/dic/registrationcategory/')
        request.user = user
        admin.site._registry[RegistrationCategory].save_model(request, category, None, True)
        for _ in range(2):
            seed(apps, SimpleNamespace(connection=connection))
        category.refresh_from_db()
        self.assertEqual((category.fee_ngn, category.early_bird_fee_ngn), (Decimal('14000'), Decimal('11000')))
        self.assertFalse(category.is_active)
        self.assertEqual(self.edition.registration_categories.count(), 5)

    def test_existing_unconfigured_fees_are_filled_without_replacing_regular_override(self):
        category = self.categories['primary']
        category.early_bird_fee_ngn = None
        category.fee_ngn = Decimal('14500')
        category.save()
        seed(apps, SimpleNamespace(connection=connection))
        category.refresh_from_db()
        self.assertEqual(category.fee_ngn, Decimal('14500'))
        self.assertEqual(category.early_bird_fee_ngn, Decimal('10000'))

    @override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
    def test_group_total_single_checkout_and_item_snapshots_in_both_periods(self):
        for early, expected in ((True, 59000), (False, 67500)):
            with self.subTest(early=early):
                self.edition.early_bird_cutoff_at = timezone.now() + timedelta(days=1 if early else -1)
                self.edition.save()
                people = [self.person('pre_primary', 5), self.person('primary', 10),
                    self.person('secondary', 16), self.person('undergraduate', 20, Participant.AcademicStatus.TERTIARY),
                    self.person('graduate_adult', 30)]
                order, token, _ = self.order(people)
                self.assertEqual(order.total_amount_ngn, Decimal(expected))
                self.assertEqual(order.items.count(), 5)
                self.assertEqual(order.current_price_revision.items.count(), 5)
                with patch('dic.payment_views.PaystackClient') as factory:
                    factory.return_value.initialize_transaction.side_effect = lambda **kwargs: {
                        'authorization_url': 'https://checkout.paystack.com/synthetic',
                        'reference': kwargs['reference']}
                    response = APIClient().post(reverse('dic:payment-initialize', args=[order.public_id]), {},
                        format='json', HTTP_AUTHORIZATION='Bearer ' + token)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(PaymentAttempt.objects.get(order=order).amount_kobo, expected * 100)
                factory.return_value.initialize_transaction.assert_called_once()

    @override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
    def test_completed_order_remains_immutable_after_fee_change_and_reseed(self):
        from .payment_views import _apply_verified_transaction
        order, token, _ = self.order([self.person('graduate_adult', 30)])
        attempt = PaymentAttempt.objects.create(order=order, reference='DIC-synthetic-approved-fee',
            amount_kobo=1800000, status=PaymentAttempt.Status.PENDING,
            price_revision=order.current_price_revision)
        provider_data = dict(id=987654, domain='test', reference=attempt.reference,
            amount=1800000, currency='NGN', status='success', paid_at=timezone.now().isoformat())
        _apply_verified_transaction(attempt.pk, provider_data)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, RegistrationOrder.PaymentStatus.PAID)
        revision_id = order.current_price_revision_id
        category = self.categories['graduate_adult']
        category.fee_ngn = Decimal('25000')
        category.early_bird_fee_ngn = Decimal('22000')
        category.save()
        seed(apps, SimpleNamespace(connection=connection))
        order.refresh_from_db()
        self.assertEqual(order.total_amount_ngn, Decimal('18000'))
        self.assertEqual(order.items.get().fee_snapshot_ngn, Decimal('18000'))
        self.assertEqual(order.current_price_revision_id, revision_id)
        self.assertEqual(order.current_price_revision.items.get().regular_fee_snapshot_ngn, Decimal('18500'))
        # Replaying verified evidence after a price edit must retain the paid amount.
        _apply_verified_transaction(attempt.pk, provider_data)
        attempt.refresh_from_db()
        self.assertEqual(attempt.amount_kobo, 1800000)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)
        response = APIClient().post(reverse('dic:payment-initialize', args=[order.public_id]), {},
            format='json', HTTP_AUTHORIZATION='Bearer ' + token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 1)

    def test_registration_rejects_ineligible_undergraduate(self):
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.order([self.person('undergraduate', 25, Participant.AcademicStatus.TERTIARY)])
        self.assertFalse(RegistrationOrder.objects.exists())
