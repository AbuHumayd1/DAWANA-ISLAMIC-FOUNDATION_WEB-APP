"""Run only in the isolated validation DB; no development participant fixtures."""
import io
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from datetime import date, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from pypdf import PdfReader
from .test_participant_portal import PortalFixtures
from .participant_services import ensure_enrollment
from .identity_cards import command, card_context
from .identity_tokens import read_token
from .models import DICAdminAuditEvent, DigitalIDIssue
from .portrait_pdf import geometry, render_pdf, house_details
from rest_framework.exceptions import PermissionDenied


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrintingTests(PortalFixtures, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.edition.housing_age_reference_date = date(2026, 12, 23)
        self.edition.save(update_fields=['housing_age_reference_date'])
        self.id_manager.is_staff = True
        self.id_manager.save(update_fields=['is_staff'])
        self.id_manager = get_user_model().objects.get(pk=self.id_manager.pk)
        self.enrollment = ensure_enrollment(self.item.pk)
        self.client.force_login(self.id_manager)
        self.export_url = reverse('dic:id-printing-export')

    def issue(self):
        return command(self.enrollment, 'issue', self.id_manager, 'Authorized isolated test.')

    def test_export_rejects_oversized_batch_before_issuance_or_media_retrieval(self):
        from .printing_api import MAX_PRINT_BATCH
        with patch('dic.printing_api.card_context') as context, patch('dic.printing_api.render_pdf') as render:
            response = self.export([str(self.enrollment.pk)] * (MAX_PRINT_BATCH + 1))
        self.assertEqual(response.status_code, 400)
        context.assert_not_called()
        render.assert_not_called()
        self.assertFalse(DigitalIDIssue.objects.exists())

    def export(self, ids=None):
        return self.client.post(self.export_url, {'enrollment_ids': ids or [str(self.enrollment.pk)]}, content_type='application/json')

    def test_actual_size_geometry_pagination_partial_pages_and_cut_marks(self):
        self.issue()
        request = RequestFactory().get('/')
        context = card_context(request, self.enrollment)
        self.assertEqual(geometry(), (90*mm, 130*mm, 6*mm))
        for count, pages in [(1, 1), (4, 1), (30, 8), (240, 60)]:
            contexts = []
            for index in range(count):
                enrollment = SimpleNamespace(edition=self.edition, participant=self.enrollment.participant,
                    participant_number=f'TEST-{index:04d}')
                contexts.append({**context, 'enrollment': enrollment})
            with patch('dic.portrait_pdf.house_details', return_value=('Housing assignment pending', None)):
                result = render_pdf(contexts)
            reader = PdfReader(io.BytesIO(result))
            self.assertEqual(len(reader.pages), pages)
            text = '\n'.join(page.extract_text() for page in reader.pages)
            for index in range(count):
                self.assertEqual(text.count(f'TEST-{index:04d}'), 1)
            for page_index, page in enumerate(reader.pages):
                self.assertAlmostEqual(float(page.mediabox.width), A4[0], places=3)
                self.assertAlmostEqual(float(page.mediabox.height), A4[1], places=3)
                operations = page.get_contents().operations
                rectangles = [args for args, op in operations if op == b're' and abs(float(args[2])-90*mm)<.01 and abs(float(args[3])-130*mm)<.01]
                expected = min(4, count-page_index*4)
                self.assertEqual(len(rectangles), expected)
                # Match isolated stroked line paths, not rounded-panel segments.
                guides = []
                for offset in range(len(operations)-2):
                    move, line, stroke = operations[offset:offset+3]
                    if move[1] == b'm' and line[1] == b'l' and stroke[1] == b'S':
                        guides.append(tuple(float(v) for v in (*move[0], *line[0])))
                expected_guides = []
                for cx, cy in [(0, 0), (90*mm, 0), (0, 130*mm), (90*mm, 130*mm)]:
                    dx, dy = (-1 if cx == 0 else 1), (-1 if cy == 0 else 1)
                    expected_guides.extend([(cx+dx*mm, cy, cx+dx*2.5*mm, cy),
                                            (cx, cy+dy*mm, cx, cy+dy*2.5*mm)])
                self.assertEqual(len(guides), expected*8)
                for guide in expected_guides:
                    self.assertEqual(sum(all(abs(a-b)<.001 for a,b in zip(actual, guide)) for actual in guides), expected)
        width, height, gap = geometry()
        self.assertGreaterEqual((A4[0]-width*2-gap)/2, 10*mm)
        self.assertGreaterEqual((A4[1]-height*2-gap)/2, 10*mm)

    def test_export_deduplicates_and_reprint_keeps_credential_and_audits(self):
        issue = self.issue()
        token = read_token(issue)
        first = self.export([str(self.enrollment.pk)]*2)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first['Content-Type'], 'application/pdf')
        self.assertEqual(first['Cache-Control'], 'private, no-store')
        event = DICAdminAuditEvent.objects.get(action='participant_ids_exported')
        self.assertEqual(event.actor, self.id_manager)
        self.assertEqual(event.details['card_count'], 1)
        self.assertEqual(event.details['enrollment_ids'], [str(self.enrollment.pk)])
        self.assertNotIn(token, str(event.details))
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='participant_ids_printed').exists())
        confirm = reverse('dic:id-printing-confirm', args=[event.target_id])
        for _ in range(2):
            self.assertEqual(self.client.post(confirm, {}, content_type='application/json').status_code, 200)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='participant_ids_printed').count(), 1)
        self.assertEqual(self.export().status_code, 200)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='participant_ids_exported').count(), 2)
        self.assertEqual(DigitalIDIssue.objects.count(), 1)
        self.assertEqual(read_token(DigitalIDIssue.objects.get()), token)

    def test_shared_authorized_issuance_and_reissue_activate_without_printing(self):
        from .participant_services import id_command
        first = id_command(self.enrollment.pk, 'issue', self.id_manager, 'Explicit staff issuance')
        first_token = read_token(first)
        self.assertEqual(id_command(self.enrollment.pk, 'issue', self.id_manager).pk, first.pk)
        replacement = id_command(self.enrollment.pk, 'reissue', self.id_manager, 'Replacement authorized')
        self.assertNotEqual(read_token(replacement), first_token)
        first.refresh_from_db()
        self.assertIsNotNone(first.revoked_at)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='participant_qr_activated').count(), 2)
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='participant_ids_exported').exists())

    def test_service_and_model_saves_require_authorized_active_staff(self):
        from .participant_services import id_command
        for actor in (None, self.operator):
            for action in ('issue', 'reissue', 'revoke'):
                with self.assertRaises(PermissionDenied):
                    id_command(self.enrollment.pk, action, actor, 'Denied action')
        for field in ('is_staff', 'is_active'):
            setattr(self.id_manager, field, False)
            with self.assertRaises(PermissionDenied):
                id_command(self.enrollment.pk, 'issue', self.id_manager)
            setattr(self.id_manager, field, True)
        with self.assertRaises(PermissionDenied):
            DigitalIDIssue.objects.create(enrollment=self.enrollment, version=1,
                issued_by=self.id_manager, expires_at=timezone.now()+timedelta(days=1))
        self.assertFalse(DigitalIDIssue.objects.exists())
        issue = self.issue()
        token = read_token(issue)
        issue.revoked_at, issue.revoked_by = timezone.now(), self.id_manager
        with self.assertRaises(PermissionDenied):
            issue.save()
        issue.refresh_from_db()
        self.assertIsNone(issue.revoked_at)
        self.assertEqual(read_token(issue), token)
        from .identity_tokens import new_token
        issue.verification_digest, issue.verification_secret = new_token()
        with self.assertRaises(PermissionDenied):
            issue.save()
        issue.refresh_from_db()
        self.assertEqual(read_token(issue), token)

    def test_portal_preparation_never_issues_even_with_staff_session_or_action(self):
        from .test_identity_cards import IdentityCardTests
        browser, _ = IdentityCardTests.portal_client(self)
        for staff_session in (False, True):
            if staff_session:
                browser.force_login(self.id_manager)
            for action in ('issue', 'reissue', 'revoke'):
                response = browser.post(reverse('dic:participant-enrollments'),
                    {'registration_item_id': self.item.pk, 'action': action}, content_type='application/json')
                self.assertEqual(response.status_code, 403)
            response = browser.post(reverse('dic:participant-enrollments'),
                {'registration_item_id': self.item.pk}, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()['issue'])
            self.assertFalse(DigitalIDIssue.objects.exists())
        issue = self.issue()
        from .participant_services import id_command
        id_command(self.enrollment.pk, 'revoke', self.id_manager, 'Authorized test revocation')
        browser.post(reverse('dic:participant-enrollments'), {'registration_item_id': self.item.pk}, content_type='application/json')
        self.assertEqual(DigitalIDIssue.objects.count(), 1)
        issue.refresh_from_db()
        self.assertIsNotNone(issue.revoked_at)

    def test_staff_api_issues_reissues_revokes_without_exposing_credentials(self):
        url = reverse('dic:operations-enrollment-id', args=[self.enrollment.pk])
        for action in ('issue', 'reissue', 'revoke'):
            result = self.client.post(url, {'action': action, 'reason': 'Authorized isolated test'}, content_type='application/json')
            self.assertEqual(result.status_code, 200)
            for issue in DigitalIDIssue.objects.all():
                for private in (read_token(issue), issue.verification_secret, issue.verification_digest):
                    self.assertNotIn(private, result.content.decode())
        self.assertEqual(DigitalIDIssue.objects.count(), 2)
        self.assertFalse(DigitalIDIssue.objects.filter(revoked_at__isnull=True).exists())

    def test_reissue_and_late_confirmation_do_not_mark_new_credential_printed(self):
        from .participant_services import id_command
        old = self.issue()
        self.assertEqual(self.export().status_code, 200)
        event = DICAdminAuditEvent.objects.get(action='participant_ids_exported')
        self.assertEqual(event.details['cards'][0]['issue_id'], str(old.pk))
        replacement = id_command(self.enrollment.pk, 'reissue', self.id_manager, 'Authorized replacement')
        self.client.post(reverse('dic:id-printing-confirm', args=[event.target_id]), {}, content_type='application/json')
        row = self.client.get(reverse('dic:id-printing')).json()['results'][0]
        self.assertEqual(row['version'], replacement.version)
        self.assertFalse(row['printed'])
        self.assertFalse(row['exported'])
        self.assertTrue(row['previously_printed'])
        self.assertEqual(self.export().status_code, 200)
        newer = DICAdminAuditEvent.objects.filter(action='participant_ids_exported').first()
        self.client.post(reverse('dic:id-printing-confirm', args=[newer.target_id]), {}, content_type='application/json')
        self.assertTrue(self.client.get(reverse('dic:id-printing')).json()['results'][0]['printed'])

    def test_legacy_history_is_preserved_without_guessing_issue_version(self):
        self.issue()
        import uuid
        batch = str(uuid.uuid4())
        details = dict(enrollment_ids=[str(self.enrollment.pk)], participant_numbers=[self.enrollment.participant_number], card_count=1, batch_id=batch)
        event = DICAdminAuditEvent.objects.create(actor=self.id_manager, action='participant_ids_exported', target_type='IDPrintBatch', target_id=batch, details=details)
        self.client.post(reverse('dic:id-printing-confirm', args=[batch]), {}, content_type='application/json')
        event.refresh_from_db()
        self.assertEqual(event.details, details)
        row = self.client.get(reverse('dic:id-printing')).json()['results'][0]
        self.assertTrue(row['legacy_history'])
        self.assertTrue(row['previously_printed'])
        self.assertFalse(row['printed'])

    def test_missing_pdf_dependency_does_not_break_directory_or_create_export_audit(self):
        import builtins
        import importlib
        from . import portrait_pdf
        original = builtins.__import__
        def without_reportlab(name, *args, **kwargs):
            if name.startswith('reportlab'):
                raise ModuleNotFoundError('reportlab unavailable')
            return original(name, *args, **kwargs)
        self.issue()
        with patch('builtins.__import__', side_effect=without_reportlab):
            importlib.reload(portrait_pdf)
            self.assertEqual(self.client.get(reverse('dic:id-printing')).status_code, 200)
            self.assertEqual(self.export().status_code, 503)
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='participant_ids_exported').exists())

    def test_missing_revoked_expired_unpaid_and_legacy_ids_rejected_without_export_audit(self):
        self.assertEqual(self.export().status_code, 400)
        issue = self.issue()
        issue.verification_digest = None
        DigitalIDIssue.objects.filter(pk=issue.pk).update(verification_digest=None)
        self.assertEqual(self.export().status_code, 400)
        command(self.enrollment, 'issue', self.id_manager, 'Explicit activation')
        issue.refresh_from_db()
        issue.expires_at = timezone.now()-timedelta(seconds=1)
        DigitalIDIssue.objects.filter(pk=issue.pk).update(expires_at=issue.expires_at)
        self.assertEqual(self.export().status_code, 400)
        command(self.enrollment, 'reissue', self.id_manager, 'Authorized replacement')
        self.paid_order.payment_attempts.update(provider_status='pending')
        self.assertEqual(self.export().status_code, 400)
        self.paid_order.payment_attempts.update(provider_status='success')
        command(self.enrollment, 'revoke', self.id_manager, 'Authorized revocation')
        self.assertEqual(self.export().status_code, 400)
        self.assertFalse(DICAdminAuditEvent.objects.filter(action='participant_ids_exported').exists())
        self.assertEqual(self.client.get(reverse('dic:id-printing')).json()['results'], [])

    def test_authorization_and_csrf_are_enforced(self):
        self.issue()
        for user in (None, self.operator):
            browser = Client()
            if user:
                browser.force_login(user)
            self.assertEqual(browser.get(reverse('dic:id-printing')).status_code, 403)
            self.assertEqual(browser.post(self.export_url, {}, content_type='application/json').status_code, 403)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.id_manager)
        self.assertEqual(browser.post(self.export_url, {}, content_type='application/json').status_code, 403)

    def test_house_colour_and_pending_house(self):
        from .models import HouseAllocation, House
        self.assertEqual(house_details(self.enrollment), ('Housing assignment pending', None))
        house = House.objects.create(edition=self.edition, name='SYNTHETIC TEST HOUSE', gender=self.enrollment.participant.sex.lower(), capacity=25, badge_colour='#123456')
        with patch('dic.identity_cards.housing', return_value=house.name):
            HouseAllocation.objects.create(edition=self.edition, participant=self.enrollment.participant, house=house, status='allocated')
            self.assertEqual(house_details(self.enrollment), (house.name, '#123456'))
            self.issue()
            context = card_context(RequestFactory().get('/'), self.enrollment)
            payload = render_pdf([context])
            operations = PdfReader(io.BytesIO(payload)).pages[0].get_contents().operations
            fills = [tuple(float(c) for c in args) for args, op in operations if op == b'rg']
            self.assertTrue(any(all(abs(a-b)<.0001 for a,b in zip(fill, (18/255,52/255,86/255))) for fill in fills))
            house.badge_colour = ''
            house.save(update_fields=['badge_colour'])
            self.assertEqual(house_details(self.enrollment), (house.name, None))

    def test_rendered_qr_decodes_to_existing_secure_verification_url(self):
        import cv2
        import fitz
        import numpy as np
        self.issue()
        context = card_context(RequestFactory().get('/'), self.enrollment)
        document = fitz.open(stream=render_pdf([context]), filetype='pdf')
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(4, 4))
        pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(pixels)
        self.assertEqual(decoded, context['verification_url'])

    def test_individual_portrait_and_portal_scope(self):
        self.issue()
        self.assertEqual(self.client.get(reverse('dic:id-card', args=[self.enrollment.pk])+'?format=portrait').status_code, 200)
        from .test_identity_cards import IdentityCardTests
        browser, _ = IdentityCardTests.portal_client(self)
        url = reverse('dic:participant-card', args=[self.enrollment.pk])+'?format=portrait'
        self.assertEqual(browser.get(url).status_code, 200)
        other = ensure_enrollment(self.unpaid_order.items.first().pk)
        self.assertEqual(browser.get(reverse('dic:participant-card', args=[other.pk])+'?format=portrait').status_code, 404)
        self.assertEqual(Client().get(url).status_code, 403)
