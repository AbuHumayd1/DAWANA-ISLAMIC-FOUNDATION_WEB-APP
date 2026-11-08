from copy import deepcopy
from datetime import date
from unittest.mock import patch
import uuid
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import GuardianRelationship, PortalAccountBooking, HousingJob
from .payment_views import _apply_verified_transaction
from .registration_guardians import approve_declared_guardians


@override_settings(PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class ExplicitGuardianTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt
    provider_result = fixtures.PaymentApiTests.provider_result

    def register_family(self):
        from .models import RegistrationOrder
        self.edition.housing_age_reference_date = date(self.edition.year, 12, 23)
        self.edition.save(update_fields=['housing_age_reference_date'])
        data = deepcopy(self.order_payload)
        adult = data['participants'][0]
        adult.update(full_name=data['primary_registrant']['full_name'],
            email=data['primary_registrant']['email'], sex='Female')
        child = {**adult, 'full_name': 'Dependent child', 'date_of_birth': date(self.edition.year-3, 1, 1).isoformat()}
        data['participants'] = [adult, child]
        data['guardian_relationships'] = [{'child_index': 1, 'guardian_index': 0, 'confirmed': True}]
        result = self.client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code, 201, result.data)
        self.order = RegistrationOrder.objects.get(public_id=result.data['order_id'])
        return GuardianRelationship.objects.get(child__registration_items__order=self.order)

    def test_only_explicit_verified_shared_booking_is_approved_and_requeued(self):
        relation = self.register_family()
        attempt = self.create_pending_attempt('family-payment')
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        actor = get_user_model().objects.create_user(username='guardian-automation', is_staff=True, is_superuser=True)
        approve_declared_guardians(self.edition.pk, actor)
        relation.refresh_from_db()
        self.assertEqual(relation.status, 'pending')  # Email is not yet proved.
        account = PortalAccountBooking.objects.get(order=self.order).account
        account.user.is_active = True
        account.user.save(update_fields=['is_active'])
        HousingJob.objects.filter(edition=self.edition).update(state='held',
            reason='A guardian relationship awaits approval; hold the entire group.')
        approve_declared_guardians(self.edition.pk, actor)
        relation.refresh_from_db()
        self.assertEqual(relation.status, 'approved')
        self.assertEqual(relation.approved_by_id, actor.pk)
        self.assertEqual(HousingJob.objects.filter(edition=self.edition, state='pending').count(), 2)

    def test_mismatching_guardian_identity_remains_pending_after_payment_and_email_proof(self):
        relation = self.register_family()
        attempt = self.create_pending_attempt('ambiguous-family')
        _apply_verified_transaction(attempt.pk, self.provider_result(attempt.reference))
        account = PortalAccountBooking.objects.get(order=self.order).account
        account.user.is_active = True
        account.user.save(update_fields=['is_active'])
        relation.guardian.full_name = 'Different adult'
        relation.guardian.save(update_fields=['full_name'])
        actor = get_user_model().objects.create_user(username='guardian-automation', is_staff=True, is_superuser=True)
        approve_declared_guardians(self.edition.pk, actor)
        relation.refresh_from_db()
        self.assertEqual(relation.status, 'pending')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
