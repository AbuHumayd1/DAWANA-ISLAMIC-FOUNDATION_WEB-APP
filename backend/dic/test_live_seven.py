from copy import deepcopy
from datetime import date
from io import StringIO
from unittest.mock import patch
import uuid
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import override_settings, TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from . import tests as fixtures
from . import test_identity_cards as identity
from .test_participant_portal import PortalFixtures
from .models import PortalAccountBooking, RegistrationOrder, GuardianRelationship
from .participant_services import ensure_enrollment


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock')
class RegistrationContinuationTests(APITestCase):
    setUp = fixtures.PaymentApiTests.setUp

    def test_repeat_contact_uses_independent_credentials_and_idempotent_order(self):
        original = PortalAccountBooking.objects.get(order=self.order).account
        payload = deepcopy(self.order_payload)
        payload['portal_account'].update(mode='create', username='different-new-username')
        key = str(uuid.uuid4())
        response = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, 201, response.data)
        other = PortalAccountBooking.objects.get(order__public_id=response.data['order_id']).account
        self.assertNotEqual(other.pk, original.pk)
        retry = self.client.post(reverse('dic:order-create'), payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data['order_id'], response.data['order_id'])

    def test_account_diagnostic_is_read_only_and_does_not_print_private_identifiers(self):
        account = PortalAccountBooking.objects.get(order=self.order).account
        from .models import DICAdminAuditEvent
        before = DICAdminAuditEvent.objects.count()
        output = StringIO()
        call_command('diagnose_dic_access', username=account.username_key, stdout=output)
        self.assertIn('"account_found": true', output.getvalue())
        for value in (account.user.password, account.contact_digest, account.username_key, self.order.primary_registrant.email):
            self.assertNotIn(value, output.getvalue())
        self.assertEqual(DICAdminAuditEvent.objects.count(), before)

    def test_management_link_is_only_exposed_to_registration_managers(self):
        from types import SimpleNamespace
        from .operations_api import _order_data
        permitted = {'dic.change_registrationorder', 'dic.can_manage_registration_access'}
        for enabled in (False, True):
            actor = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False, has_perm=lambda name: enabled and name in permitted)
            data = _order_data(self.order, actor, include_detail=True)
            self.assertEqual('management_url' in data, enabled)
            if enabled:
                self.assertEqual(data['management_url'], reverse('admin:dic_registration_cleanup', args=[self.order.pk]))


@override_settings(FRONTEND_ORIGIN='https://dawanaislamicfoundation.org')
class IDReturnAndGuardianTests(PortalFixtures, TestCase):
    issue = identity.IdentityCardTests.issue
    portal_client = identity.IdentityCardTests.portal_client
    portal_card_url = identity.IdentityCardTests.portal_card_url

    def setUp(self):
        super().setUp()
        self.id_manager.is_staff = True
        self.id_manager.save(update_fields=['is_staff'])
        self.enrollment = ensure_enrollment(self.item.pk)
        self.client.force_login(self.id_manager)

    def test_operations_return_is_fixed_and_foreign_return_url_is_ignored(self):
        self.issue()
        url = reverse('dic:id-card', args=[self.enrollment.pk])
        response = self.client.get(url, {'return_to': 'operations'})
        expected = 'https://dawanaislamicfoundation.org/dic/operations/participant-ids?enrollment=' + str(self.enrollment.pk)
        self.assertEqual(response.context_data['return_url'], expected)
        response = self.client.get(url, {'return_to': 'https://evil.invalid/'})
        self.assertEqual(response.context_data['return_url'], reverse('admin:dic_campenrollment_changelist'))
        browser, _ = self.portal_client()
        response = browser.get(self.portal_card_url(), {'return_to': 'operations'})
        self.assertEqual(response.context_data['return_url'], 'https://dawanaislamicfoundation.org/dic/participant?view=digital-id&camper=' + str(self.enrollment.pk))

    def test_approved_child_document_does_not_require_house_or_housing_configuration(self):
        from .housing_service import review_guardian
        child = self.enrollment.participant
        child.date_of_birth, child.sex = date(2022, 1, 1), 'Male'
        child.save()
        guardian_item = self.paid_order.items.exclude(pk=self.item.pk).first()
        guardian = guardian_item.participant
        guardian.date_of_birth, guardian.sex = date(1990, 1, 1), 'Female'
        guardian.save()
        ensure_enrollment(guardian_item.pk)
        self.id_manager.user_permissions.add(Permission.objects.get(codename='can_approve_housing_guardians'))
        relation = GuardianRelationship.objects.create(edition=self.edition, child=child, guardian=guardian, reason='Synthetic approval')
        review_guardian(relation.pk, self.id_manager, 'approved', 'Synthetic reviewed relation')
        self.issue()
        # 2026 document rules have a fixed reference; housing may remain unset.
        self.edition.year = 2026
        self.edition.housing_age_reference_date = None
        self.edition.save(update_fields=['year', 'housing_age_reference_date'])
        browser, _ = self.portal_client()
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 200)
        relation.status = 'revoked'
        GuardianRelationship.objects.filter(pk=relation.pk).update(status='revoked')
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 200)
