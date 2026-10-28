import io
import secrets
import tempfile
from pathlib import Path
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import ValidationError
from .test_participant_portal import PortalFixtures, TEST_DELIVERY
from .models import CampEnrollment, DigitalIDIssue, DICAdminAuditEvent, GuardianRelationship
from .participant_services import ensure_enrollment, eligibility
from .identity_cards import command
from .identity_tokens import read_token
from .housing_service import review_guardian
from .identity_views import card_pages, render_cards
from .identity_branding import official_logo_data


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IdentityCardTests(PortalFixtures, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # The shared operations fixture intentionally creates non-staff users.
        # These tests exercise Django Admin, which additionally requires staff
        # status. Keep the operator unprivileged for IDs; do not use superusers.
        for user in (self.id_manager, self.operator):
            user.is_staff = True
            user.save(update_fields=['is_staff'])
        self.id_manager = get_user_model().objects.get(pk=self.id_manager.pk)
        self.operator = get_user_model().objects.get(pk=self.operator.pk)
        self.assertTrue(self.id_manager.is_active and self.id_manager.is_staff)
        self.assertFalse(self.id_manager.is_superuser)
        self.assertTrue(self.id_manager.has_perm('dic.can_view_dic_ids'))
        self.assertTrue(self.id_manager.has_perm('dic.can_manage_dic_ids'))
        self.assertFalse(self.operator.has_perm('dic.can_view_dic_ids'))
        self.assertFalse(self.operator.has_perm('dic.can_manage_dic_ids'))
        self.edition.housing_age_reference_date = date(2026, 12, 23)
        self.edition.save(update_fields=['housing_age_reference_date'])
        self.enrollment = ensure_enrollment(self.item.pk)
        self.client.force_login(self.id_manager)
        self.card_url = reverse('dic:id-card', args=[self.enrollment.pk])

    def issue(self):
        return command(self.enrollment, 'issue', self.id_manager, 'Authorized test issuance.')

    def verification(self, token, client=None):
        return (client or self.client).post(reverse('dic:verify-id'), {'token': token}, content_type='application/json')

    def save_print_fixture(self, response, filename):
        directory = getattr(settings, 'DIC_ID_PRINT_QA_DIR', None)
        if directory:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            response.context_data['demo'] = True
            (directory / filename).write_text(response.rendered_content, encoding='utf-8')

    def test_unique_participant_numbers_and_idempotent_enrollment(self):
        self.assertEqual(ensure_enrollment(self.item.pk).pk, self.enrollment.pk)
        other_item = self.paid_order.items.exclude(pk=self.item.pk).first()
        other = ensure_enrollment(other_item.pk)
        self.assertNotEqual(other.participant_number, self.enrollment.participant_number)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampEnrollment.objects.create(participant=other.participant, edition=self.edition,
                source_item=other_item, participant_number=self.enrollment.participant_number)

    def test_unverified_payment_does_not_issue_an_active_card(self):
        self.paid_order.payment_attempts.update(provider_status='pending')
        with self.assertRaises(ValidationError):
            self.issue()
        self.assertFalse(DigitalIDIssue.objects.exists())
        response = self.client.get(self.card_url)
        self.assertNotContains(response, 'Secure verification QR code')

    def test_real_card_generation_without_photo_and_with_pending_housing(self):
        self.issue()
        response = self.client.get(self.card_url)
        self.assertContains(response, self.enrollment.participant_number)
        self.assertContains(response, 'Photograph not supplied')
        self.assertContains(response, 'Housing assignment pending')
        self.assertContains(response, 'data:image/svg+xml;base64,')
        self.assertContains(response, 'DAWANA ISLAMIC FOUNDATION')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        for private in ('Confidential participant address', self.enrollment.participant.phone, self.enrollment.participant.email):
            self.assertNotContains(response, private)

    def test_private_portrait_renders_and_admin_does_not_use_public_storage_url(self):
        adult = self.enrollment.participant
        adult.date_of_birth = date(1990, 1, 1)
        adult.save(update_fields=['date_of_birth'])
        self.issue()
        with tempfile.TemporaryDirectory() as media, override_settings(DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=media):
            image = io.BytesIO()
            Image.new('RGB', (20, 20), color='green').save(image, format='JPEG')
            self.enrollment.portrait.save('synthetic-test.jpg', SimpleUploadedFile('synthetic-test.jpg', image.getvalue(), content_type='image/jpeg'))
            response = self.client.get(self.card_url)
            self.assertContains(response, 'data:image/jpeg;base64,')
            self.save_print_fixture(response, 'adult-with-synthetic-test-photo.html')
            self.assertEqual(self.client.get(reverse('admin:dic_campenrollment_change', args=[self.enrollment.pk])).status_code, 200)

    def test_print_and_self_contained_html_download(self):
        self.issue()
        response = self.client.get(self.card_url + '?download=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertContains(response, '@media print')
        self.assertContains(response, 'window.print()')
        self.assertContains(response, 'data:image/svg+xml;base64,')

    def test_tokens_are_random_opaque_and_encrypted_at_rest(self):
        issue = self.issue()
        token = read_token(issue)
        self.assertEqual(len(token), 43)
        self.assertNotEqual(issue.verification_secret, token)
        self.assertNotIn(token, issue.verification_secret)
        self.assertNotIn(self.enrollment.participant_number, token)
        self.assertEqual(self.verification(token).status_code, 200)
        self.assertNotIn(token, str(list(DICAdminAuditEvent.objects.values_list('details', flat=True))))

    def test_public_verification_is_minimal_and_unauthorized_staff_get_no_details(self):
        token = read_token(self.issue())
        public = Client()
        self.assertEqual(set(self.verification(token, public).json()), {'status', 'edition'})
        public.force_login(self.operator)
        self.assertEqual(set(self.verification(token, public).json()), {'status', 'edition'})
        self.assertEqual(public.get(self.card_url).status_code, 403)

    def test_authorized_verification_has_only_required_identification_details(self):
        result = self.verification(read_token(self.issue())).json()
        self.assertEqual(result['participant_number'], self.enrollment.participant_number)
        self.assertEqual(result['name'], self.enrollment.participant.full_name)
        self.assertEqual(result['house'], 'Housing assignment pending')
        for field in ('date_of_birth', 'phone', 'address', 'guardian', 'payment_status'):
            self.assertNotIn(field, result)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='participant_qr_verified').exists())

    def test_invalid_revoked_expired_tokens_share_generic_failure(self):
        issue = self.issue()
        token = read_token(issue)
        invalid = self.verification(secrets.token_urlsafe(32))
        command(self.enrollment, 'revoke', self.id_manager, 'Lost card.')
        revoked = self.verification(token)
        self.assertEqual((invalid.status_code, invalid.json()), (revoked.status_code, revoked.json()))
        replacement = command(self.enrollment, 'reissue', self.id_manager, 'Authorized replacement.')
        DigitalIDIssue.objects.filter(pk=replacement.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verification(read_token(replacement)).status_code, 404)

    def test_reissue_preserves_participant_id_and_revokes_old_qr(self):
        original = self.issue()
        old = read_token(original)
        replacement = command(self.enrollment, 'reissue', self.id_manager, 'Lost original card.')
        self.assertEqual(replacement.version, original.version + 1)
        self.assertNotEqual(read_token(replacement), old)
        self.assertEqual(self.verification(old).status_code, 404)
        self.assertEqual(self.verification(read_token(replacement)).status_code, 200)
        self.assertEqual(self.verification(old).status_code, 404)
        self.assertEqual(CampEnrollment.objects.get(pk=self.enrollment.pk).participant_number, self.enrollment.participant_number)

    def test_eligibility_is_rechecked_after_issuance(self):
        token = read_token(self.issue())
        self.paid_order.payment_attempts.update(provider_status='failed')
        self.assertEqual(self.verification(token).status_code, 404)
        self.assertNotContains(self.client.get(self.card_url), 'Secure verification QR code')

    def test_legacy_qr_activation_requires_explicit_staff_post(self):
        issue = self.issue()
        DigitalIDIssue.objects.filter(pk=issue.pk).update(verification_digest=None, verification_secret='')
        self.assertNotContains(self.client.get(self.card_url), 'Secure verification QR code')
        issue.refresh_from_db()
        self.assertIsNone(issue.verification_digest)
        activated = self.issue()
        self.assertTrue(activated.verification_digest)

    def test_child_has_own_id_with_approved_guardian_without_child_login(self):
        child = self.enrollment.participant
        child.date_of_birth = date(2022, 1, 1)
        child.sex = 'Male'
        child.save()
        other_item = self.paid_order.items.exclude(pk=self.item.pk).first()
        guardian = other_item.participant
        guardian.date_of_birth, guardian.sex = date(1990, 1, 1), 'Female'
        guardian.save()
        self.id_manager.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', content_type__model='guardianrelationship',
            codename='can_approve_housing_guardians'))
        # Permission caches on an already-used User are not cleared by M2M.add().
        self.id_manager = get_user_model().objects.get(pk=self.id_manager.pk)
        self.assertTrue(self.id_manager.has_perm('dic.can_approve_housing_guardians'))
        relation = GuardianRelationship.objects.create(edition=self.edition, child=child, guardian=guardian, reason='Synthetic test guardian proposal.')
        review_guardian(relation.pk, self.id_manager, 'approved', 'Verified test guardian.')
        guardian_record = ensure_enrollment(other_item.pk)
        self.assertNotEqual(self.enrollment.participant_number, guardian_record.participant_number)
        self.issue()
        self.assertContains(self.client.get(self.card_url), self.enrollment.participant_number)
        self.assertContains(self.client.get(reverse('admin:dic_campenrollment_changelist')), guardian.full_name)

    def test_permission_enforcement_for_manage_and_directory(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('admin:dic_id_manage', args=[self.enrollment.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:dic_campenrollment_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:dic_digitalidissue_changelist')).status_code, 403)
        # ID permissions alone must not grant Django Admin access to a non-staff
        # account. A login redirect is correct for this different negative case.
        self.id_manager.is_staff = False
        self.id_manager.save(update_fields=['is_staff'])
        with self.assertRaises(DjangoPermissionDenied):
            self.issue()
        self.client.force_login(self.id_manager)
        response = self.client.get(reverse('admin:dic_id_manage', args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/admin/login/'))

    def test_public_scans_do_not_change_registration_or_allocation_state(self):
        from .models import HouseAllocation
        issue = self.issue()
        before = (self.paid_order.status, self.paid_order.payment_status, HouseAllocation.objects.count())
        self.verification(read_token(issue), Client())
        self.paid_order.refresh_from_db()
        self.assertEqual(before, (self.paid_order.status, self.paid_order.payment_status, HouseAllocation.objects.count()))

    def test_batch_issue_and_print_multiple_eligible_records(self):
        other = ensure_enrollment(self.paid_order.items.exclude(pk=self.item.pk).first().pk)
        response = self.client.post(reverse('admin:dic_campenrollment_changelist'), {
            'action': 'issue_and_print', '_selected_action': [str(self.enrollment.pk), str(other.pk)], 'index': '0'})
        self.assertContains(response, self.enrollment.participant_number)
        self.assertContains(response, other.participant_number)
        self.assertEqual(DigitalIDIssue.objects.filter(revoked_at__isnull=True).count(), 2)

    def test_verification_csrf_and_rate_limit(self):
        token = read_token(self.issue())
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(self.verification(token, browser).status_code, 403)
        page = browser.get(reverse('dic:verify-id'))
        self.assertContains(page, 'location.hash')
        self.assertContains(page, 'history.replaceState')
        response = browser.post(reverse('dic:verify-id'), {'token': token}, content_type='application/json',
                                HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        for _ in range(30):
            response = self.verification('invalid')
        self.assertEqual(response.status_code, 429)

    def test_replacement_requires_reason_and_unknown_action_is_rejected(self):
        self.issue()
        for action, reason in [('reissue', ''), ('revoke', ''), ('unknown', 'Denied')]:
            with self.assertRaises(ValidationError):
                command(self.enrollment, action, self.id_manager, reason)

    def test_logo_asset_embedding_is_offline_and_missing_asset_is_honest(self):
        # A plain synthetic image tests the embedding mechanism, not logo design.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-logo.png'
            Image.new('RGB', (20, 20), color='white').save(path)
            with override_settings(DIC_ID_LOGO_FILE=path):
                self.assertTrue(official_logo_data().startswith('data:image/png;base64,'))
                self.issue()
                response = self.client.get(self.card_url + '?download=1')
                self.assertContains(response, 'alt="Official Dawana Islamic Foundation logo"')
                self.assertContains(response, 'data:image/png;base64,')
                self.assertNotContains(response, 'src="https://')
                self.assertNotContains(response, 'src="http://')
            with override_settings(DIC_ID_LOGO_FILE=Path(directory) / 'missing.png'):
                self.assertIsNone(official_logo_data())
                self.assertContains(self.client.get(self.card_url), 'no substitute logo is used')

    def test_long_synthetic_name_and_assigned_house_are_preserved(self):
        from .models import House
        from .allocation import assign_participant
        person = self.enrollment.participant
        person.full_name = 'SYNTHETIC — ' + 'Abdulrahman Olayiwola Muhammad ' * 4
        person.save(update_fields=['full_name'])
        self.id_manager.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', content_type__model='houseallocation', codename='can_allocate_participants'))
        self.id_manager = get_user_model().objects.get(pk=self.id_manager.pk)
        house = House.objects.create(edition=self.edition, name='SYNTHETIC PRINT TEST HOUSE', gender=person.sex.lower(), capacity=25)
        assign_participant(person.pk, self.edition.pk, house.pk, self.id_manager, reason='Synthetic print test only.')
        self.issue()
        response = self.client.get(self.card_url)
        self.assertContains(response, person.full_name)
        self.assertContains(response, house.name)
        self.save_print_fixture(response, 'long-name-assigned-house.html')

    def test_a4_page_groups_cover_partial_and_multiple_pages_without_empty_pages(self):
        for count, expected in [(0, []), (1, [1]), (7, [7]), (8, [8]), (9, [8, 1]), (16, [8, 8]), (17, [8, 8, 1]), (25, [8, 8, 8, 1])]:
            self.assertEqual([len(page) for page in card_pages(list(range(count)))], expected)
        self.issue()
        request = RequestFactory().get(self.card_url)
        request.user = self.id_manager
        from unittest.mock import patch
        from types import SimpleNamespace
        from .identity_cards import card_context
        context = card_context(request, self.enrollment)
        # Unique synthetic rendering inputs; no extra registration/payment rows.
        inputs = [SimpleNamespace(pk=index) for index in range(17)]
        with patch('dic.identity_views.card_context', return_value=context):
            response = render_cards(request, inputs, batch=True)
        response.context_data['demo'] = True
        response.render()
        self.assertEqual([len(page) for page in response.context_data['pages']], [8, 8, 1])
        self.assertContains(response, 'class="print-page"', count=3)
        self.assertContains(response, 'class="card-frame"', count=17)
        self.assertContains(response, 'width:85.6mm;height:54mm')
        self.assertContains(response, 'SYNTHETIC DEMO')
        # This deliberately tests legacy PVC pagination, not the portrait PDF.
        self.save_print_fixture(response, 'legacy-pvc-batch-17-three-pages.html')

    def test_individual_and_batch_download_have_distinct_print_modes(self):
        self.issue()
        individual = self.client.get(self.card_url + '?download=1')
        self.assertContains(individual, 'Standard PVC card')
        self.assertContains(individual, 'layout-single')
        self.assertContains(individual, 'browser headers and footers off')
        self.assertContains(individual, '100% scale')
        batch = self.client.get(self.card_url + '?layout=batch&download=1')
        self.assertContains(batch, 'Batch printing')
        self.assertTrue(batch.context_data['batch'])
        self.assertEqual(len(batch.context_data['pages']), 1)
        self.assertContains(batch, 'data:image/svg+xml;base64,')
        self.save_print_fixture(individual, 'single-card.html')
        self.save_print_fixture(batch, 'batch-one-card.html')

    def test_both_formats_share_qr_and_render_without_any_database_writes(self):
        from unittest.mock import patch
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        issue = self.issue()
        with CaptureQueriesContext(connection) as queries:
            pvc = self.client.get(self.card_url)
            a6 = self.client.get(self.card_url + '?format=a6')
            downloaded = self.client.get(self.card_url + '?format=a6&download=1')
        self.assertEqual(pvc.status_code, 200)
        self.assertEqual(a6.status_code, 200)
        self.assertEqual(pvc.context_data['cards'][0]['qr'], a6.context_data['cards'][0]['qr'])
        self.assertEqual(pvc.context_data['cards'][0]['verification_url'], a6.context_data['cards'][0]['verification_url'])
        self.assertEqual(a6.context_data['cards'][0]['issue'].pk, issue.pk)
        self.assertEqual(DigitalIDIssue.objects.count(), 1)
        writes = [row['sql'] for row in queries if row['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))]
        self.assertEqual(writes, [])
        self.assertContains(downloaded, 'width:105mm;height:148mm')
        self.assertContains(a6, 'format-a6')
        self.save_print_fixture(a6, 'a6-single.html')

    def test_invalid_format_and_printer_are_rejected_and_legacy_url_stays_pvc(self):
        self.issue()
        self.assertEqual(self.client.get(self.card_url + '?format=giant').status_code, 400)
        self.assertEqual(self.client.get(self.card_url + '?format=a6&printer=shrink').status_code, 400)
        self.assertEqual(self.client.get(self.card_url).context_data['card_format'], 'pvc')

    def test_a6_batch_modes_paginate_without_scaling_or_duplicate_identities(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from .identity_cards import card_context
        for count, lengths in [(1, [1]), (4, [4]), (5, [4, 1]), (8, [4, 4]), (9, [4, 4, 1])]:
            self.assertEqual([len(page) for page in card_pages(list(range(count)), 4)], lengths)
        self.issue()
        request = RequestFactory().get(self.card_url)
        request.user = self.id_manager
        context = card_context(request, self.enrollment)
        inputs = [SimpleNamespace(pk=index) for index in range(9)]
        with patch('dic.identity_views.card_context', return_value=context):
            response = render_cards(request, inputs, batch=True, card_format='a6')
            standard = render_cards(request, inputs, batch=True, card_format='a6', printer='standard')
        response.render()
        standard.render()
        self.assertEqual([len(page) for page in response.context_data['pages']], [4, 4, 1])
        self.assertEqual([len(page) for page in standard.context_data['pages']], [2, 2, 2, 2, 1])
        self.assertContains(response, 'Borderless A4 required')
        self.assertContains(standard, 'landscape A4')
        self.save_print_fixture(response, 'a6-four-up-nine-fixtures.html')
        self.save_print_fixture(standard, 'a6-standard-printer-nine-fixtures.html')
        unique = render_cards(request, [self.enrollment, self.enrollment], batch=True)
        self.assertEqual(len(unique.context_data['cards']), 1)

    def test_unicode_labels_and_participant_name_survive_utf8_download(self):
        self.enrollment.participant.full_name = 'SYNTHETIC — عبد الرحمن Ọláyíwọlá'
        self.enrollment.participant.save(update_fields=['full_name'])
        self.issue()
        response = self.client.get(self.card_url + '?format=a6&download=1')
        self.assertEqual(response.charset, 'utf-8')
        self.assertIn(self.enrollment.participant.full_name, response.content.decode('utf-8'))
        self.assertContains(response, '&times;')
        self.assertNotContains(response, '85.6 ? 54')
        self.assertNotContains(response, ' ? PARTICIPANT')

    def test_local_database_diagnostic_requires_development_loopback_and_secret(self):
        import os
        from unittest.mock import patch
        from django.db import connection
        route = reverse('dic:local-preview-database')
        with patch.dict(os.environ, {'DAWANA_LOCAL_DIAGNOSTIC_TOKEN': 'synthetic-diagnostic-test-token'}), override_settings(DEBUG=True, SETTINGS_MODULE='config.settings.development'):
            self.assertEqual(self.client.get(route).status_code, 404)
            response = self.client.get(route, HTTP_X_DAWANA_LOCAL_DIAGNOSTIC='synthetic-diagnostic-test-token')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['database'], connection.settings_dict['NAME'])
            self.assertEqual(set(response.json()), {'database', 'synthetic'})
            self.assertEqual(self.client.get(route, REMOTE_ADDR='203.0.113.1', HTTP_X_DAWANA_LOCAL_DIAGNOSTIC='synthetic-diagnostic-test-token').status_code, 404)
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get(route, HTTP_X_DAWANA_LOCAL_DIAGNOSTIC='synthetic-diagnostic-test-token').status_code, 404)

    def test_shared_credential_revocation_applies_to_both_physical_formats(self):
        issue = self.issue()
        old_token = read_token(issue)
        command(self.enrollment, 'revoke', self.id_manager, 'Synthetic dual-format revocation.')
        for suffix in ('', '?format=a6'):
            self.assertNotContains(self.client.get(self.card_url + suffix), 'Secure verification QR code')
        replacement = command(self.enrollment, 'reissue', self.id_manager, 'Synthetic dual-format replacement.')
        pvc = self.client.get(self.card_url)
        badge = self.client.get(self.card_url + '?format=a6')
        self.assertEqual(pvc.context_data['cards'][0]['issue'].pk, replacement.pk)
        self.assertEqual(badge.context_data['cards'][0]['issue'].pk, replacement.pk)
        self.assertEqual(self.verification(old_token).status_code, 404)

        self.assertEqual(self.verification(read_token(replacement)).status_code, 200)
        self.assertEqual(self.verification(old_token).status_code, 404)

    def portal_client(self):
        from .models import ParticipantPortalGrant, ParticipantPortalScope
        from .security import digest_value
        from .recovery_views import _contact_digest
        from .participant_api import COOKIE, COOKIE_PATH
        token = secrets.token_urlsafe(32)
        grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value(token), channel='email',
            contact_digest=_contact_digest('email', self.paid_order.primary_registrant.email),
            expires_at=timezone.now() + timedelta(minutes=20))
        ParticipantPortalScope.objects.create(grant=grant, order=self.paid_order)
        browser = Client()
        browser.cookies[COOKIE] = token
        browser.cookies[COOKIE]['path'] = COOKIE_PATH
        return browser, grant

    def portal_card_url(self, enrollment=None):
        return reverse('dic:participant-card', args=[(enrollment or self.enrollment).pk])

    @override_settings(**TEST_DELIVERY)
    def test_portal_actual_verified_booking_login_can_download_existing_card(self):
        self.issue()
        browser, _ = self.login()
        response = browser.get(self.portal_card_url() + '?download=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.enrollment.participant_number)
        self.assertContains(response, 'My Digital ID')
        self.assertNotContains(response, '/admin/dic/')
        self.assertNotContains(response, 'Issue / replace / revoke')
        self.assertContains(response, 'data:image/svg+xml;base64,')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_portal_download_uses_shared_credential_and_never_issues_on_get(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.issue()
        browser, _ = self.portal_client()
        admin = self.client.get(self.card_url)
        with CaptureQueriesContext(connection) as queries:
            pvc = browser.get(self.portal_card_url())
            explicit_pvc = browser.get(self.portal_card_url() + '?format=pvc&download=1')
            badge = browser.get(self.portal_card_url() + '?format=a6&download=1')
        self.assertEqual(pvc.status_code, 200)
        self.assertEqual(explicit_pvc.status_code, 200)
        self.assertEqual(badge.status_code, 200)
        self.assertEqual(explicit_pvc.context_data['cards'][0]['qr'], admin.context_data['cards'][0]['qr'])
        self.assertEqual(pvc.context_data['cards'][0]['qr'], admin.context_data['cards'][0]['qr'])
        self.assertEqual(badge.context_data['cards'][0]['qr'], admin.context_data['cards'][0]['qr'])
        self.assertFalse(any(row['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for row in queries))
        self.assertEqual(DigitalIDIssue.objects.count(), 1)

    def test_portal_missing_revoked_and_ineligible_ids_never_issue(self):
        browser, _ = self.portal_client()
        self.assertNotContains(browser.get(self.portal_card_url()), 'Secure verification QR code')
        self.assertFalse(DigitalIDIssue.objects.exists())
        self.issue()
        command(self.enrollment, 'revoke', self.id_manager, 'Portal regression revocation.')
        self.assertNotContains(browser.get(self.portal_card_url()), 'Secure verification QR code')
        self.assertEqual(DigitalIDIssue.objects.count(), 1)
        command(self.enrollment, 'reissue', self.id_manager, 'Authorized replacement.')
        self.paid_order.payment_attempts.update(provider_status='pending')
        self.assertNotContains(browser.get(self.portal_card_url()), 'Secure verification QR code')

    def test_portal_rejects_other_bookings_and_invalid_or_revoked_grants(self):
        from .models import ParticipantPortalScope
        self.issue()
        browser, grant = self.portal_client()
        stranger = ensure_enrollment(self.unpaid_order.items.first().pk)
        self.assertEqual(browser.get(self.portal_card_url(stranger)).status_code, 404)
        self.assertEqual(browser.get(self.portal_card_url(stranger) + '?format=bulk').status_code, 404)
        self.assertEqual(Client().get(self.portal_card_url()).status_code, 403)
        self.assertEqual(Client().get(self.portal_card_url() + '?format=bulk').status_code, 403)
        self.assertEqual(self.client.get(self.portal_card_url()).status_code, 403)  # Staff session is not a portal grant.
        self.assertEqual(browser.get(self.portal_card_url() + '?format=bulk').status_code, 400)
        original_expiry = grant.expires_at
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save(update_fields=['expires_at'])
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 403)
        grant.expires_at = original_expiry
        grant.save(update_fields=['expires_at'])
        ParticipantPortalScope.objects.filter(grant=grant).update(revoked_at=timezone.now())
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 404)

    def test_portal_approved_guardian_can_download_scoped_child_without_child_login(self):
        child = self.enrollment.participant
        child.date_of_birth, child.sex = date(2022, 1, 1), 'Male'
        child.save()
        guardian_item = self.paid_order.items.exclude(pk=self.item.pk).first()
        guardian = guardian_item.participant
        guardian.date_of_birth, guardian.sex = date(1990, 1, 1), 'Female'
        guardian.save()
        ensure_enrollment(guardian_item.pk)
        self.id_manager.user_permissions.add(Permission.objects.get(codename='can_approve_housing_guardians'))
        self.id_manager = get_user_model().objects.get(pk=self.id_manager.pk)
        relation = GuardianRelationship.objects.create(edition=self.edition, child=child, guardian=guardian, reason='Synthetic guardian download test.')
        review_guardian(relation.pk, self.id_manager, 'approved', 'Synthetic approval.')
        self.issue()
        browser, _ = self.portal_client()
        self.assertContains(browser.get(self.portal_card_url() + '?format=a6'), self.enrollment.participant_number)
        review_guardian(relation.pk, self.id_manager, 'revoked', 'Synthetic withdrawal.')
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 403)

    def test_portal_booking_contact_alone_does_not_establish_dependent_guardianship(self):
        self.enrollment.participant.date_of_birth = date(2022, 1, 1)
        self.enrollment.participant.save()
        self.issue()
        browser, _ = self.portal_client()
        self.assertEqual(browser.get(self.portal_card_url()).status_code, 403)

    def test_portal_download_does_not_expand_to_cross_booking_guardian_links(self):
        self.issue()
        browser, grant = self.portal_client()
        from .models import ParticipantPortalScope
        # Even another booking with the exact same verified contact remains unscoped.
        self.unpaid_order.primary_registrant.email = self.paid_order.primary_registrant.email
        self.unpaid_order.primary_registrant.save()
        other = ensure_enrollment(self.unpaid_order.items.first().pk)
        self.assertEqual(browser.get(self.portal_card_url(other)).status_code, 404)

    def test_clean_printing_ui_has_optional_help_and_no_single_page_caption(self):
        self.issue()
        response = self.client.get(self.card_url)
        self.assertContains(response, '<details class="printing-help">')
        self.assertContains(response, 'Return to Participant Directory')
        self.assertNotContains(response, 'Individual card')
        self.assertNotContains(response, 'printed ID works without a participant smartphone')
