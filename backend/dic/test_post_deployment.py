"""Focused post-deployment safety and issued-card regressions."""
from datetime import date
from django.contrib.auth import get_user_model
from django.test import override_settings, TestCase
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APITestCase
from . import tests as fixtures
from . import test_identity_cards as identity
from .test_participant_portal import PortalFixtures
from .models import RegistrationOrder, PortalAccountBooking
from .registration_cleanup import review_registration


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class CleanupTests(APITestCase):
    create_pending_attempt = fixtures.PaymentApiTests.create_pending_attempt

    def setUp(self):
        cache.clear()
        fixtures.PaymentApiTests.setUp(self)

    def manager(self):
        return get_user_model().objects.create_superuser(username='cleanup-owner', password='synthetic-owner-password')

    def test_review_cancel_restore_retains_records_and_invalidates_old_credentials(self):
        actor = self.manager()
        original = self.order.access_token_digest
        review_registration(self.order.pk, actor, 'cancel', 'Synthetic unwanted booking')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertIsNotNone(self.order.access_token_revoked_at)
        self.assertTrue(PortalAccountBooking.objects.filter(order=self.order).exists())
        review_registration(self.order.pk, actor, 'restore', 'Synthetic owner requested restoration')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertNotEqual(self.order.access_token_digest, original)
        self.assertLessEqual(self.order.access_token_expires_at, timezone.now())
        self.assertIsNone(self.order.access_token_revoked_at)

    def test_cancel_denies_payment_attempts_paid_tutors_and_unauthorized_staff(self):
        ordinary = get_user_model().objects.create_user(username='cleanup-outsider')
        with self.assertRaises(PermissionDenied):
            review_registration(self.order.pk, ordinary, 'cancel', 'Denied')
        actor = self.manager()
        for change in ({'payment_status': 'paid'},):
            RegistrationOrder.objects.filter(pk=self.order.pk).update(**change)
            with self.assertRaises(ValidationError):
                review_registration(self.order.pk, actor, 'cancel', 'Denied')
            RegistrationOrder.objects.filter(pk=self.order.pk).update(payment_status='pending', registration_basis='paid')
        self.create_pending_attempt()
        with self.assertRaises(ValidationError):
            review_registration(self.order.pk, actor, 'cancel', 'Pending provider outcome')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')

    def test_cleanup_admin_requires_individual_confirmation_and_permissions(self):
        actor = self.manager()
        self.client.force_login(actor)
        url = reverse('admin:dic_registration_cleanup', args=[self.order.pk])
        response = self.client.post(url, {'action': 'cancel', 'reason': 'Synthetic'})
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        response = self.client.post(url, {'action': 'cancel', 'reason': 'Synthetic', 'confirm': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')

    def test_checked_in_participant_cannot_be_cancelled(self):
        from .models import CampCheckIn
        actor = self.manager()
        CampCheckIn.objects.create(participant=self.order.items.first().participant,
            edition=self.order.edition, checked_in_by=actor)
        with self.assertRaises(ValidationError):
            review_registration(self.order.pk, actor, 'cancel', 'Must remain protected')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')

    def test_cancellation_removes_only_active_operational_visibility(self):
        from .operations_api import _apply_order_filters
        actor = self.manager()
        review_registration(self.order.pk, actor, 'cancel', 'Synthetic abandoned booking')
        base = RegistrationOrder.objects.filter(pk=self.order.pk)
        self.assertFalse(_apply_order_filters(base, {'archive': 'active'}, actor).exists())
        self.assertTrue(_apply_order_filters(base, {'archive': 'all'}, actor).exists())


class PortalIssuedIDTests(PortalFixtures, TestCase):
    issue = identity.IdentityCardTests.issue
    portal_client = identity.IdentityCardTests.portal_client
    portal_card_url = identity.IdentityCardTests.portal_card_url

    def setUp(self):
        super().setUp()
        cache.clear()
        self.id_manager.is_staff = True
        self.id_manager.save(update_fields=['is_staff'])
        from .participant_services import ensure_enrollment
        self.enrollment = ensure_enrollment(self.item.pk)

    def test_2026_adult_id_does_not_require_housing_configuration(self):
        self.issue()
        # Production defect: document access depended on housing setup even
        # for an already issued adult card. No records are approved by this read.
        self.edition.year = 2026
        self.edition.housing_age_reference_date = None
        self.edition.save(update_fields=['year', 'housing_age_reference_date'])
        browser, _ = self.portal_client()
        metadata = browser.get(reverse('dic:participant-id', args=[self.enrollment.pk]))
        self.assertEqual(metadata.status_code, 200, metadata.content)
        for kind in ('pvc', 'a6'):
            card = browser.get(self.portal_card_url() + '?format=' + kind)
            self.assertEqual(card.status_code, 200, card.content)
            self.assertContains(card, self.enrollment.participant_number)

    def test_unpaid_or_foreign_id_never_becomes_visible_after_reference_fix(self):
        self.issue()
        browser, _ = self.portal_client()
        other = self.unpaid_order.items.first().enrollments.first()
        if other:
            self.assertEqual(browser.get(self.portal_card_url(other)).status_code, 404)
        self.paid_order.payment_status = 'pending'
        self.paid_order.save(update_fields=['payment_status'])
        self.assertIn(browser.get(self.portal_card_url()).status_code, (403, 404))
