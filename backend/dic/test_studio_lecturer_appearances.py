"""Media Studio lecturer appearance workflow acceptance and permission tests."""
import json
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CampEdition, DICAdminAuditEvent
from .showcase_models import Lecturer, LecturerAppearance
from .test_memories import image_file


class MediaStudioLecturerAppearanceTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        override = override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=self.storage.name)
        override.enable()
        self.addCleanup(override.disable)
        self.edition = CampEdition.objects.create(
            name='Historical camp edition', year=2024, is_active=False,
            camp_start_date=date(2024, 12, 23), camp_end_date=date(2025, 1, 1))
        self.lecturer = Lecturer.objects.create(
            name='Synthetic Historical Lecturer',
            photograph=image_file(),
            alt_text='Synthetic portrait',
            biography='Synthetic biography',
        )
        self.editor = get_user_model().objects.create_user(
            username='appearance-editor', password='test-password', is_staff=True)
        self.publisher = get_user_model().objects.create_user(
            username='appearance-publisher', password='test-password', is_staff=True)
        self.verifier = get_user_model().objects.create_user(
            username='appearance-verifier', password='test-password', is_staff=True)
        for u in (self.editor, self.publisher, self.verifier):
            for name in ('view_lecturerappearance', 'view_lecturer', 'add_lecturerappearance',
                         'change_lecturerappearance'):
                u.user_permissions.add(Permission.objects.get(codename=name))
        self.publisher.user_permissions.add(
            Permission.objects.get(codename='publish_lecturerappearance'))
        self.verifier.user_permissions.add(
            Permission.objects.get(codename='verify_lecturerappearance'))
        self.list_url = reverse('dic:studio-lecturer-appearances')

    def post(self, url, payload, user):
        self.client.force_login(user)
        return self.client.post(url, json.dumps(payload), content_type='application/json')

    def patch(self, url, payload, user):
        self.client.force_login(user)
        return self.client.patch(url, json.dumps(payload), content_type='application/json')

    def make_record(self):
        response = self.post(self.list_url, {
            'lecturer': self.lecturer.pk, 'edition': self.edition.pk,
            'participation_type': 'previous',
            'topic': 'Historically verified only when evidenced',
        }, self.editor)
        self.assertEqual(response.status_code, 201, response.content)
        return LecturerAppearance.objects.get(pk=response.json()['item']['id'])

    def detail_url(self, record):
        return reverse('dic:studio-lecturer-appearance-detail', args=[record.pk])

    def test_cannot_create_without_authentication_or_grants(self):
        anonymous = self.client.post(
            self.list_url,
            json.dumps({'lecturer': self.lecturer.pk, 'edition': self.edition.pk,
                        'participation_type': 'previous'}),
            content_type='application/json')
        self.assertIn(anonymous.status_code, (401, 403))
        ordinary = get_user_model().objects.create_user(username='ordinary', password='test-password')
        denied = self.post(self.list_url, {
            'lecturer': self.lecturer.pk, 'edition': self.edition.pk,
            'participation_type': 'previous'}, ordinary)
        self.assertEqual(denied.status_code, 403)

    def test_editor_can_create_draft_but_cannot_publish_or_verify(self):
        record = self.make_record()
        self.assertEqual(record.state, 'draft')
        self.assertEqual(self.client.get(reverse('dic:showcase')).status_code, 200)
        self.assertFalse(self.client.get(reverse('dic:showcase')).json()['previous'])
        response = self.post(self.detail_url(record), {'action': 'publish'}, self.editor)
        self.assertEqual(response.status_code, 403)
        response = self.post(self.detail_url(record), {'action': 'verify'}, self.editor)
        self.assertEqual(response.status_code, 403)

    def test_verify_then_publish_previous_edition_and_withdraw(self):
        record = self.make_record()
        self.assertEqual(self.patch(self.detail_url(record), {
            'verification_note': 'Approved archive programme and committee register.',
            'featured': True, 'display_order': 3,
        }, self.editor).status_code, 200)
        self.assertEqual(self.post(self.detail_url(record), {
            'action': 'verify'}, self.verifier).status_code, 200)
        record.refresh_from_db()
        self.assertTrue(record.verified)
        self.assertEqual(record.state, 'review')
        self.assertEqual(self.post(self.detail_url(record), {
            'action': 'publish'}, self.publisher).status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.state, 'published')
        response = self.client.get(reverse('dic:showcase'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['previous']), 1)
        self.assertEqual(response.json()['previous'][0]['topic'], record.topic)
        self.assertEqual(self.post(self.detail_url(record), {
            'action': 'withdraw'}, self.publisher).status_code, 200)
        self.assertEqual(self.client.get(reverse('dic:showcase')).json()['previous'], [])
        self.assertTrue(DICAdminAuditEvent.objects.filter(
            target_type='LecturerAppearance', target_id=str(record.pk),
            action='showcase_withdrawn').exists())

    def test_historical_topic_hidden_until_verified(self):
        record = self.make_record()
        self.assertEqual(self.post(self.detail_url(record), {'action': 'publish'}, self.publisher).status_code, 200)
        rows = self.client.get(reverse('dic:showcase')).json()['previous']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['topic'], '')
        self.assertFalse(rows[0]['confirmed'])

    def test_duplicate_edition_and_unsupported_confirmation_rejected(self):
        self.make_record()
        response = self.post(self.list_url, {
            'lecturer': self.lecturer.pk, 'edition': self.edition.pk,
            'participation_type': 'previous'}, self.editor)
        self.assertEqual(response.status_code, 400)
        response = self.post(self.list_url, {
            'lecturer': self.lecturer.pk, 'edition': self.edition.pk,
            'participation_type': 'previous', 'confirmation_status': 'confirmed'}, self.editor)
        self.assertEqual(response.status_code, 400)

    def test_published_edit_goes_to_review(self):
        record = self.make_record()
        self.post(self.detail_url(record), {'action': 'publish'}, self.publisher)
        response = self.patch(self.detail_url(record), {'topic': 'Revised topic'}, self.editor)
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.state, 'review')
        self.assertEqual(self.client.get(reverse('dic:showcase')).json()['previous'], [])

    def test_verification_rejects_blank_evidence(self):
        record = self.make_record()
        response = self.post(self.detail_url(record), {'action': 'verify'}, self.verifier)
        self.assertEqual(response.status_code, 400)
        record.refresh_from_db()
        self.assertFalse(record.verified)

    def test_different_edition_transfer_rejected(self):
        record = self.make_record()
        other = CampEdition.objects.create(name='Another edition', year=2023,
            camp_start_date=date(2023, 12, 23), camp_end_date=date(2024, 1, 1))
        response = self.patch(self.detail_url(record), {'edition': other.pk}, self.editor)
        self.assertEqual(response.status_code, 400)
