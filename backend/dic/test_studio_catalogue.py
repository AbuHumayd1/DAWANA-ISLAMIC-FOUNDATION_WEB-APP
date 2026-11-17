"""Foundation catalogue acceptance using disposable synthetic media and database.

No production media, real R2 account or camper identity is referenced.
"""
from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from dic.models import CampEdition, CampPhotograph, DICAdminAuditEvent
from dic.staff_roles import ROLES
from dic.studio_models import StudioAsset, StudioPlacement


class StudioCatalogueTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            'catalogue-owner', 'owner@example.test', 'synthetic')
        self.operator = get_user_model().objects.create_user(
            'catalogue-media', password='synthetic', is_staff=True)
        group = Group.objects.create(name='DAWANA Media Studio Personnel')
        for entry in ROLES[group.name]:
            app, code = entry.split('.')
            group.permissions.add(Permission.objects.get(
                content_type__app_label=app, codename=code))
        self.operator.groups.add(group)
        self.edition = CampEdition.objects.create(name='Synthetic Edition 2038', year=2038,
            camp_start_date='2038-12-23', camp_end_date='2039-01-01', is_active=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.operator)
        self.csrf = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']

    def post(self, name, data, args=None):
        return self.client.post(reverse('dic:' + name, args=args or []),
                                data, content_type='application/json',
                                HTTP_X_CSRFTOKEN=self.csrf)

    def photo(self, title='Synthetic photograph'):
        image = Image.new('RGB', (20, 20), '#235b39')
        stream = BytesIO()
        image.save(stream, format='JPEG')
        file = SimpleUploadedFile('synthetic.jpg', stream.getvalue(), content_type='image/jpeg')
        return CampPhotograph.objects.create(
            edition=self.edition, photograph=file, caption=title, alt_text='Synthetic green square')

    def test_link_once_place_twice_and_withdraw_only_one_destination(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo()
            photo.state = 'published'
            photo.save(actor=self.operator)
            first = self.post('studio-assets', {'source_kind': 'photos', 'source_id': photo.pk})
            self.assertEqual(first.status_code, 201, first.content)
            asset_id = first.json()['asset']['id']
            again = self.post('studio-assets', {'source_kind': 'photos', 'source_id': photo.pk})
            self.assertEqual(again.status_code, 200)
            self.assertEqual(StudioAsset.objects.count(), 1)
            target = [asset_id]
            archive = self.post('studio-placements', {
                'destination': 'foundation_archive', 'action': 'publish'}, args=target)
            self.assertEqual(archive.status_code, 200, archive.content)
            home = self.post('studio-placements', {
                'destination': 'foundation_home', 'action': 'publish'}, args=target)
            self.assertEqual(home.status_code, 200, home.content)
            self.assertEqual(StudioPlacement.objects.filter(state='published').count(), 2)
            public_url = reverse('dic:studio-public-placements')
            self.assertEqual(len(self.client.get(public_url, {'destination': 'foundation_archive'}).json()['items']), 1)
            result = self.post('studio-placements', {
                'destination': 'foundation_home', 'action': 'withdraw'}, args=target)
            self.assertEqual(result.status_code, 200, result.content)
            self.assertEqual(StudioPlacement.objects.filter(state='published').count(), 1)
            self.assertEqual(len(self.client.get(public_url, {'destination': 'foundation_archive'}).json()['items']), 1)
            self.assertEqual(len(self.client.get(public_url, {'destination': 'foundation_home'}).json()['items']), 0)
            photo.state = 'draft'
            photo.save(actor=self.operator)
            self.assertEqual(len(self.client.get(public_url, {'destination': 'foundation_archive'}).json()['items']), 0)

    def test_edition_boundary_and_no_camper_public_metadata(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo()
            photo.state = 'published'
            photo.save(actor=self.operator)
            asset_id = self.post('studio-assets', {'source_kind': 'photos', 'source_id': photo.pk}).json()['asset']['id']
            wrong = CampEdition.objects.create(name='Other synthetic', year=2040,
                camp_start_date='2040-12-23', camp_end_date='2041-01-01')
            denied = self.post('studio-placements', {
                'destination': 'dic_memories', 'edition': wrong.pk, 'action': 'publish'}, args=[asset_id])
            self.assertEqual(denied.status_code, 400)
            allowed = self.post('studio-placements', {
                'destination': 'dic_memories', 'edition': self.edition.pk, 'action': 'publish'}, args=[asset_id])
            self.assertEqual(allowed.status_code, 200, allowed.content)
            self.assertEqual(self.client.get(reverse('dic:studio-public-placements'),
                              {'destination': 'camper_resources'}).status_code, 404)

    def test_archive_is_atomic_and_publication_does_not_resurrect(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo()
            photo.state = 'published'
            photo.save(actor=self.operator)
            asset_id = self.post('studio-assets', {'source_kind': 'photos', 'source_id': photo.pk}).json()['asset']['id']
            self.post('studio-placements', {'destination': 'foundation_archive', 'action': 'publish'}, args=[asset_id])
            archive = self.post('studio-asset-detail', {'action': 'archive'}, args=[asset_id])
            self.assertEqual(archive.status_code, 200)
            self.assertTrue(StudioAsset.objects.get(pk=asset_id).archived_at)
            self.assertEqual(StudioPlacement.objects.get(asset_id=asset_id).state, 'withdrawn')
            denied = self.post('studio-placements', {'destination': 'foundation_archive', 'action': 'publish'}, args=[asset_id])
            self.assertEqual(denied.status_code, 400)
            self.post('studio-asset-detail', {'action': 'restore'}, args=[asset_id])
            self.assertEqual(StudioPlacement.objects.get(asset_id=asset_id).state, 'withdrawn')
            self.assertTrue(DICAdminAuditEvent.objects.filter(action='studio_asset_archive').exists())

    def test_linked_recording_requires_current_camper_placement_even_if_source_stays_published(self):
        from dic.camp_release_models import LectureRecording
        from dic.camp_release_api import studio_audio_visible
        audio = LectureRecording.objects.create(
            edition=self.edition, title='Synthetic studio lecture',
            audio='camp-recordings/not-a-real-upload.mp3')
        audio.state = 'published'
        audio.save(actor=self.operator)
        self.assertTrue(studio_audio_visible(audio, self.edition))  # Legacy unlinked content preserved.
        asset_id = self.post('studio-assets', {
            'source_kind': 'recordings', 'source_id': audio.pk}).json()['asset']['id']
        self.assertFalse(studio_audio_visible(audio, self.edition))
        published = self.post('studio-placements', {
            'destination': 'camper_resources', 'edition': self.edition.pk,
            'action': 'publish'}, args=[asset_id])
        self.assertEqual(published.status_code, 200, published.content)
        self.assertTrue(studio_audio_visible(audio, self.edition))
        self.post('studio-placements', {'destination': 'camper_resources',
            'edition': self.edition.pk, 'action': 'withdraw'}, args=[asset_id])
        self.assertFalse(studio_audio_visible(audio, self.edition))
        self.assertEqual(self.client.get(reverse('dic:studio-public-placements'),
                         {'destination': 'camper_resources'}).status_code, 404)

    def test_catalogue_pages_are_bounded_and_source_permission_filtered(self):
        for n in range(32):
            StudioAsset.objects.create(
                source_kind='photos', source_id=10000 + n,
                title=f'Fixture {n}', created_by=self.owner)
        response = self.client.get(reverse('dic:studio-assets'), {'page': 1})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()['assets']), 30)
        self.assertTrue(response.json()['has_more'])
        last = self.client.get(reverse('dic:studio-assets'), {'page': 2})
        self.assertEqual(len(last.json()['assets']), 2)
        self.assertFalse(last.json()['has_more'])
        self.assertEqual(self.client.get(reverse('dic:studio-assets'), {'page': 101}).status_code, 400)

    def test_library_pages_bound_query_and_do_not_expose_private_file_keys(self):
        with TemporaryDirectory() as root, override_settings(
                DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            for n in range(32):
                self.photo(title=f'Private fixture {n}')
            page_one = self.client.get(reverse('dic:studio-library'), {
                'library': 'photos', 'page': 1})
            self.assertEqual(page_one.status_code, 200, page_one.content)
            self.assertEqual(len(page_one.json()['items']), 30)
            self.assertTrue(page_one.json()['has_more'])
            self.assertNotIn('memories/', str(page_one.content))
            page_two = self.client.get(reverse('dic:studio-library'), {
                'library': 'photos', 'page': 2})
            self.assertEqual(len(page_two.json()['items']), 2)
            self.assertFalse(page_two.json()['has_more'])
            self.assertEqual(self.client.get(reverse('dic:studio-library'), {
                'library': 'photos', 'page': 101}).status_code, 400)

    def test_unprivileged_studio_viewer_cannot_link_or_publish(self):
        viewer = get_user_model().objects.create_user('catalogue-viewer', password='synthetic', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_campphotograph'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('dic:studio-assets')).status_code, 403)
        self.assertEqual(self.post('studio-assets', {'source_kind': 'photos', 'source_id': 1}).status_code, 403)
