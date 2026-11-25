"""Regression checks for the staff-first lecturer publishing flow."""
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dic.models import CampEdition, DICAdminAuditEvent
from dic.showcase_models import Lecturer, LecturerAppearance
from dic.staff_roles import ROLES


def flyer():
    output = BytesIO()
    Image.new('RGB', (400, 520), '#d8f0e2').save(output, format='JPEG')
    return SimpleUploadedFile('lecturer-flyer.jpg', output.getvalue(), content_type='image/jpeg')


class SimpleStudioLecturerTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(
            'lecturer-media-staff', password='synthetic', is_staff=True)
        group = Group.objects.create(name='DAWANA Media Studio Personnel')
        for item in ROLES[group.name]:
            app, code = item.split('.')
            group.permissions.add(Permission.objects.get(
                content_type__app_label=app, codename=code))
        self.operator.groups.add(group)
        self.edition = CampEdition.objects.create(
            name='Lecturer DIC Synthetic', year=2038,
            camp_start_date='2038-12-23', camp_end_date='2039-01-01')
        self.client = Client()
        self.client.force_login(self.operator)

    def test_staff_can_publish_flyer_without_profile_or_verification_steps(self):
        with TemporaryDirectory() as directory, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=directory,
            DIC_PRODUCTION_STORAGE=False), patch('dic.studio_lecturer_api.upload_enabled', return_value=True):
            response = self.client.post(reverse('dic:studio-simple-lecturers'), {
                'flyer': flyer(), 'edition': str(self.edition.pk), 'participation_type': 'previous'
            })
            self.assertEqual(response.status_code, 201, response.content)
            item = LecturerAppearance.objects.get(pk=response.json()['item']['id'])
            self.assertEqual(item.state, 'published')
            self.assertEqual(item.lecturer.name, 'Lecturer')
            self.assertEqual(item.lecturer.biography, '')
            self.assertFalse(item.verified)
            self.assertEqual(self.client.get(reverse('dic:showcase')).status_code, 200)
            self.assertEqual(DICAdminAuditEvent.objects.filter(
                action='studio_lecturer_created_published', target_id=str(item.pk)).count(), 1)
            # Preview/editing does not require creating a second identity.
            revised = self.client.patch(reverse('dic:studio-simple-lecturer-detail', args=[item.pk]),
                data={'name': 'Shaykh Synthetic', 'biography': 'Brief approved description'})
            self.assertEqual(revised.status_code, 200, revised.content)
            item.refresh_from_db()
            self.assertEqual(item.state, 'published')
            self.assertEqual(item.lecturer.name, 'Shaykh Synthetic')
            withdrawn = self.client.post(reverse('dic:studio-lecturer-appearance-detail', args=[item.pk]),
                data='{"action":"withdraw"}', content_type='application/json')
            self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
            item.refresh_from_db()
            self.assertEqual(item.state, 'review')
            republished = self.client.post(reverse('dic:studio-lecturer-appearance-detail', args=[item.pk]),
                data='{"action":"publish"}', content_type='application/json')
            self.assertEqual(republished.status_code, 200, republished.content)
            removed = self.client.delete(reverse('dic:studio-simple-lecturer-detail', args=[item.pk]))
            self.assertEqual(removed.status_code, 200, removed.content)
            self.assertFalse(LecturerAppearance.objects.filter(pk=item.pk).exists())
            self.assertEqual(DICAdminAuditEvent.objects.filter(
                action='studio_lecturer_deleted', target_id=str(item.pk)).count(), 1)

    def test_invalid_or_missing_flyer_returns_explanatory_error(self):
        with patch('dic.studio_lecturer_api.upload_enabled', return_value=True):
            response = self.client.post(reverse('dic:studio-simple-lecturers'), {
                'edition': str(self.edition.pk), 'participation_type': 'previous'
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn('Choose the lecturer flyer', response.content.decode())

    def test_unprivileged_staff_cannot_publish_or_delete(self):
        outsider = get_user_model().objects.create_user(
            'lecturer-viewer', password='synthetic', is_staff=True)
        outsider.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_lecturerappearance'))
        self.client.force_login(outsider)
        response = self.client.post(reverse('dic:studio-simple-lecturers'), {
            'edition': str(self.edition.pk), 'flyer': flyer()
        })
        self.assertEqual(response.status_code, 403)
