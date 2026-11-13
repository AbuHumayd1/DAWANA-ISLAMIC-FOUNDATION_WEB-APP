from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib import admin
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from .models import HouseScoreTransaction
from .registration_age import validate_guardian_contact
from .participant_api import PortalMeView, PortalEnrollmentsView


class ConsolidatedPolicyTests(SimpleTestCase):
    def test_participant_email_is_optional_but_booking_email_remains_required(self):
        from .test_checkout_validation import CheckoutValidationTests
        from .serializers import RegistrationOrderCreateSerializer
        data = CheckoutValidationTests().payload()
        data['participants'][0].pop('email')
        form = RegistrationOrderCreateSerializer(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        data['primary_registrant'].pop('email')
        self.assertFalse(RegistrationOrderCreateSerializer(data=data).is_valid())

    def test_guardian_boundary_and_existing_contact_preservation(self):
        for birth, required in ((date(2010, 12, 24), True), (date(2010, 12, 23), False),
                (date(2009, 12, 23), False), (date(2008, 12, 23), False), (None, False)):
            people = [{'date_of_birth': birth}]
            if required:
                with self.assertRaises(ValidationError):
                    validate_guardian_contact(people, {})
            else:
                validate_guardian_contact(people, {})
            contact = {'full_name': 'Saved Guardian', 'phone': '+234 801 234 5678'}
            before = contact.copy()
            validate_guardian_contact(people, contact)
            self.assertEqual(contact, before)

    def test_portal_read_views_reuse_only_current_authorization_result(self):
        grant = SimpleNamespace(expires_at=timezone.now() + timedelta(minutes=10), pk='synthetic', authorized_orders=[])
        for view in (PortalMeView, PortalEnrollmentsView):
            with patch('dic.participant_api.authorized_grant', return_value=grant), patch('dic.participant_api.scoped_orders') as again, patch('dic.participant_api.record'):
                response = view.as_view()(APIRequestFactory().get('/synthetic/'))
                self.assertEqual(response.status_code, 200)
                again.assert_not_called()

    def test_score_admin_never_allows_raw_ledger_edit_or_delete(self):
        model_admin = admin.site._registry[HouseScoreTransaction]
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, is_active=True, is_staff=False))
        self.assertFalse(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_pending_verification_guidance_requires_a_correct_password(self):
        from unittest.mock import Mock
        from rest_framework.exceptions import AuthenticationFailed
        from . import portal_accounts as accounts
        account = SimpleNamespace(user=SimpleNamespace(is_active=False, check_password=Mock(return_value=True)))
        with patch.object(accounts.PortalAccount.objects, 'select_related') as query, patch('dic.registration_accounts.pending_registration', return_value=True) as pending:
            query.return_value.filter.return_value.first.return_value = account
            with self.assertRaises(AuthenticationFailed) as caught:
                accounts.password_account('synthetic', 'correct-password')
            self.assertIn('still needs verification', str(caught.exception))
            account.user.check_password.return_value = False
            pending.reset_mock()
            with self.assertRaises(AuthenticationFailed) as caught:
                accounts.password_account('synthetic', 'wrong-password')
            self.assertNotIn('still needs verification', str(caught.exception))
            pending.assert_not_called()


class ScoringAdminIntegrationTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from .test_allocation import AllocationFixtures
        from .models import House
        self.edition = AllocationFixtures.make_edition(self)
        self.other = AllocationFixtures.make_edition(self, year=2099)
        self.house = House.objects.create(edition=self.edition, name='Synthetic House', gender='male', capacity=25)
        self.user = get_user_model().objects.create_user(username='score-staff', password='synthetic', is_staff=True)
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='dic',
            codename__in=['can_view_dic_operations', 'can_view_dic_scores', 'can_record_dic_scores', 'can_correct_dic_scores']))
        self.client.force_login(self.user)

    def test_admin_uses_services_with_idempotent_awards_and_append_only_corrections(self):
        import uuid
        from django.urls import reverse
        data = dict(edition=self.edition.pk, house=self.house.pk, entry_type='award', points=7,
            activity='Synthetic agreed adjustment', request_id=str(uuid.uuid4()))
        url = reverse('admin:dic_score_record')
        for _ in range(2):
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(HouseScoreTransaction.objects.count(), 1)
        entry = HouseScoreTransaction.objects.get()
        response = self.client.post(reverse('admin:dic_score_reverse', args=[entry.pk]),
            dict(reason='Synthetic correction', request_id=str(uuid.uuid4())))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HouseScoreTransaction.objects.count(), 2)
        self.assertEqual(HouseScoreTransaction.objects.get(reverses=entry).entry_type, 'deduction')
        response = self.client.get(reverse('admin:dic_score_standings'), {'edition': self.edition.pk})
        self.assertContains(response, 'Synthetic House')
        self.assertEqual(response.context_data['rows'][0]['net'], 0)
        response = self.client.post(url, {**data, 'edition': self.other.pk, 'request_id': str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'belonging to this camp edition')
        self.assertEqual(HouseScoreTransaction.objects.count(), 2)

    def test_viewer_cannot_write_and_participant_cannot_enter_admin(self):
        from django.contrib.auth.models import Permission
        from django.urls import reverse
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='dic',
            codename__in=['can_view_dic_operations', 'can_view_dic_scores']))
        self.assertEqual(self.client.get(reverse('admin:dic_score_record')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:dic_housescoretransaction_changelist')).status_code, 200)
        self.user.is_staff = False
        self.user.save(update_fields=['is_staff'])
        self.assertEqual(self.client.get(reverse('admin:dic_score_standings')).status_code, 302)
