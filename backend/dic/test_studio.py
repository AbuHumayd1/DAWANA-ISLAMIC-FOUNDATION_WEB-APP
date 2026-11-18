"""Standalone Media Studio acceptance: authenticates media-only staff without DIC ops
grants; no storage credentials or media objects leave the bounded inventory."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase, override_settings
from pathlib import Path
import tempfile
import wave
from django.urls import reverse
from dic.camp_release_models import LectureRecording
from dic.models import CampEdition
from dic.staff_roles import ROLES


class StudioAccessTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            'studio-owner', 'owner@example.test', 'synthetic')
        self.operator = get_user_model().objects.create_user(
            'media-only', password='synthetic', is_staff=True)
        group = Group.objects.create(name='DAWANA Media Studio Personnel')
        for entry in ROLES[group.name]:
            app, code = entry.split('.')
            grant = Permission.objects.get(content_type__app_label=app, codename=code)
            group.permissions.add(grant)
        self.operator.groups.add(group)
        self.client = Client(enforce_csrf_checks=True)

    def login(self, username, password='synthetic'):
        token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
        return self.client.post(reverse('dic:studio-login'),
                                {'username': username, 'password': password},
                                content_type='application/json', HTTP_X_CSRFTOKEN=token)

    def test_media_operator_is_allowed_without_registration_or_finance(self):
        response = self.login('media-only')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['owner'])
        self.assertIn('recordings', response.json()['libraries'])
        self.assertFalse(self.operator.has_perm('dic.can_view_dic_finance'))
        self.assertFalse(self.operator.has_perm('dic.delete_registrationorder'))
        self.assertEqual(self.client.get(reverse('dic:studio-me')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dic:operations-me')).status_code, 403)

    def test_owner_has_all_media_libraries_without_group_membership(self):
        response = self.login('studio-owner')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['owner'])
        from dic.studio_api import LIBRARIES
        self.assertEqual(set(response.json()['libraries']), set(LIBRARIES))
        self.assertIn('hosted', response.json()['libraries'])

    def test_camper_and_anonymous_user_cannot_browse_library(self):
        response = self.client.get(reverse('dic:studio-library'))
        self.assertIn(response.status_code, (401, 403))
        camper = get_user_model().objects.create_user('studio-camper', password='synthetic')
        self.client.force_login(camper)
        self.assertEqual(self.client.get(reverse('dic:studio-library')).status_code, 403)

    def test_login_denied_without_permission_or_csrf(self):
        camper = get_user_model().objects.create_user('camper-studio', password='synthetic', is_staff=True)
        self.assertEqual(self.login(camper.username).status_code, 401)
        self.assertEqual(self.client.post(reverse('dic:studio-login'),
                        {'username': self.owner.username, 'password': 'synthetic'},
                        content_type='application/json').status_code, 403)

    def test_bounded_inventory_and_direct_publication_audit(self):
        self.client.force_login(self.operator)
        edition = CampEdition.objects.create(
            name='Studio Synthetic Edition', year=2036,
            camp_start_date='2036-12-23', camp_end_date='2037-01-01')
        record = LectureRecording.objects.create(
            edition=edition, title='Synthetic private recording',
            audio='camp-recordings/private-secret.mp3')
        response = self.client.get(reverse('dic:studio-library'), {'library': 'recordings'})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['items'][0]['title'], record.title)
        self.assertNotIn('private-secret.mp3', str(body))
        self.assertNotIn('r2.cloudflarestorage.com', str(body))
        token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
        endpoint = reverse('dic:studio-publication', args=['recordings', record.pk])
        with tempfile.TemporaryDirectory() as root, override_settings(
                DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            folder = Path(root) / 'camp-recordings'
            folder.mkdir()
            with wave.open(str(folder / 'private-secret.wav'), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b'\\x00\\x00' * 800)
            record.audio = 'camp-recordings/private-secret.wav'
            record.save(update_fields=['audio'])
            response = self.client.post(endpoint, {'action': 'publish'},
                                        content_type='application/json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 200, response.content)
            record.refresh_from_db()
            self.assertEqual(record.state, 'published')
            self.assertEqual(record.published_by_id, self.operator.pk)
            response = self.client.post(endpoint, {'action': 'withdraw'},
                                        content_type='application/json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.state, 'draft')
        self.assertEqual(record.published_by_id, None)

    def test_studio_editor_cannot_modify_edition_or_sensitive_source_fields(self):
        self.client.force_login(self.operator)
        edition = CampEdition.objects.create(name='Editorial Synthetic', year=2035,
            camp_start_date='2035-12-23', camp_end_date='2036-01-01')
        from dic.showcase_models import CampActivity
        item = CampActivity.objects.create(edition=edition, title='Camp panel',
                                           category='Lecture', description='Approved')
        token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
        url = reverse('dic:studio-metadata', args=['activities', item.pk])
        invalid = self.client.patch(url, {'edition': 1}, content_type='application/json',
                                    HTTP_X_CSRFTOKEN=token)
        self.assertEqual(invalid.status_code, 400)
        response = self.client.patch(url, {'title': 'Revised camp panel'}, content_type='application/json',
                                     HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertEqual(item.title, 'Revised camp panel')
        self.assertEqual(item.edition_id, edition.pk)

    @override_settings(DIC_MEDIA_STUDIO_UPLOADS_ENABLED=False)
    def test_uploads_fail_closed_without_explicit_owner_r2_activation(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('dic:studio-uploads'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['enabled'])
        token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
        response = self.client.post(reverse('dic:studio-uploads'),
                                    {'library': 'photos', 'caption': 'Should not upload'},
                                    HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('r2.cloudflarestorage.com', str(response.content))

    def test_private_preview_is_streamed_only_to_authorized_studio_staff(self):
        self.client.force_login(self.operator)
        edition = CampEdition.objects.create(
            name='Studio private preview', year=2034,
            camp_start_date='2034-12-23', camp_end_date='2035-01-01')
        with tempfile.TemporaryDirectory() as root, override_settings(
                DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            folder = Path(root) / 'camp-recordings'
            folder.mkdir()
            (folder / 'staff-preview.mp3').write_bytes(b'ID3synthetic-audio')
            recording = LectureRecording.objects.create(
                edition=edition, title='Private draft preview',
                audio='camp-recordings/staff-preview.mp3')
            url = reverse('dic:studio-private-preview', args=['recordings', recording.pk])
            listing = self.client.get(reverse('dic:studio-library'), {'library': 'recordings'})
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()['items'][0]['preview_url'], url)
            self.assertNotIn('staff-preview.mp3', str(listing.content))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'audio/mpeg')
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            response.close()
            download = self.client.get(url + '?download=1')
            self.assertEqual(download.status_code, 200)
            self.assertIn('attachment', download['Content-Disposition'])
            download.close()
            self.assertEqual(self.client.get(reverse(
                'dic:studio-private-preview', args=['photos', recording.pk])).status_code, 404)
            outsider = Client()
            self.assertIn(outsider.get(url).status_code, (401, 403))
            other = get_user_model().objects.create_user(
                'unrelated-staff', password='synthetic', is_staff=True)
            outsider.force_login(other)
            self.assertEqual(outsider.get(url).status_code, 403)

    def test_nonpublisher_cannot_publish_even_if_can_view(self):
        viewer = get_user_model().objects.create_user('studio-viewer', password='synthetic', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_lecturerecording'))
        self.client.force_login(viewer)
        token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
        response = self.client.post(reverse('dic:studio-publication', args=['recordings', 1]),
                                    {'action': 'publish'}, content_type='application/json',
                                    HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 403)
