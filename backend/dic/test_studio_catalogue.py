"""Foundation catalogue acceptance using disposable synthetic media and database.

No production media, real R2 account or camper identity is referenced.
"""
from datetime import date
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
            camp_start_date=date(2038, 12, 23), camp_end_date=date(2039, 1, 1), is_active=True)
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

    def test_homepage_media_is_server_capped_at_three_without_losing_archive(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            for n in range(5):
                photo = self.photo('Synthetic homepage item ' + str(n))
                photo.state = 'published'
                photo.save(actor=self.operator)
                asset_id = self.post('studio-assets', {
                    'source_kind': 'photos', 'source_id': photo.pk}).json()['asset']['id']
                for destination in ('foundation_archive', 'foundation_home'):
                    response = self.post('studio-placements', {
                        'destination': destination, 'action': 'publish'}, args=[asset_id])
                    self.assertEqual(response.status_code, 200, response.content)
            endpoint = reverse('dic:studio-public-placements')
            home = self.client.get(endpoint, {'destination': 'foundation_home'})
            self.assertEqual(home.status_code, 200)
            self.assertEqual(len(home.json()['items']), 3)
            self.assertFalse(home.json()['has_more'])
            self.assertEqual(self.client.get(endpoint, {
                'destination': 'foundation_home', 'page': 2}).json()['items'], [])
            archive = self.client.get(endpoint, {'destination': 'foundation_archive'})
            self.assertEqual(len(archive.json()['items']), 5)

    def test_public_archive_page_is_bounded_and_private_destination_is_not_enumerable(self):
        url = reverse('dic:studio-public-placements')
        first = self.client.get(url, {'destination': 'foundation_archive', 'page': 1})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['items'], [])
        self.assertEqual(first.json()['page'], 1)
        self.assertFalse(first.json()['has_more'])
        self.assertEqual(self.client.get(url, {'destination': 'foundation_archive', 'page': 101}).status_code, 400)
        self.assertEqual(self.client.get(url, {'destination': 'foundation_archive', 'page': '1 OR 1=1'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'destination': 'camper_resources', 'page': 1}).status_code, 404)

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

    def test_public_audio_requires_separate_published_archive_placement_and_withdraws(self):
        from pathlib import Path
        from dic.camp_release_models import LectureRecording
        from dic.camp_release_api import studio_audio_visible
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            file_path = Path(root) / 'camp-recordings' / 'synthetic.mp3'
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b'ID3synthetic-public-audio')
            audio = LectureRecording.objects.create(
                edition=self.edition, title='Synthetic released lecture',
                audio='camp-recordings/synthetic.mp3')
            audio.state = 'published'
            audio.save(actor=self.operator)
            asset_id = self.post('studio-assets', {
                'source_kind': 'recordings', 'source_id': audio.pk}).json()['asset']['id']
            media_url = reverse('dic:studio-public-audio', args=[asset_id])
            anonymous = Client()
            self.assertEqual(anonymous.get(media_url).status_code, 404)
            self.assertFalse(studio_audio_visible(audio, self.edition))
            edited = self.client.patch(reverse('dic:studio-asset-detail', args=[asset_id]),
                {'programme': 'dic', 'event': ''}, content_type='application/json',
                HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(edited.status_code, 200, edited.content)
            response = self.post('studio-placements', {
                'destination': 'foundation_archive', 'action': 'publish'}, args=[asset_id])
            self.assertEqual(response.status_code, 200, response.content)
            self.assertFalse(studio_audio_visible(audio, self.edition))
            archive = anonymous.get(reverse('dic:studio-public-placements'),
                                    {'destination': 'foundation_archive'})
            self.assertEqual(len(archive.json()['items']), 1)
            self.assertEqual(archive.json()['items'][0]['programme'], 'dic')
            self.assertEqual(archive.json()['items'][0]['url'], media_url)
            streamed = anonymous.get(media_url + '?download=1')
            self.assertEqual(streamed.status_code, 200)
            self.assertIn('attachment', streamed['Content-Disposition'])
            self.assertEqual(b''.join(streamed.streaming_content), b'ID3synthetic-public-audio')
            self.post('studio-placements', {
                'destination': 'foundation_archive', 'action': 'withdraw'}, args=[asset_id])
            self.assertEqual(anonymous.get(media_url).status_code, 404)
            self.assertEqual(anonymous.get(reverse('dic:studio-public-placements'),
                                      {'destination': 'foundation_archive'}).json()['items'], [])

    def test_session_linked_camper_audio_cannot_be_published_to_public_archive(self):
        from datetime import date, time
        from dic.models import TimetableEntry
        from dic.camp_release_models import LectureRecording
        private_session = TimetableEntry.objects.create(
            edition=self.edition, date=date(2038, 12, 24), day_number=2,
            timetable_type='activities', source_key='synthetic:private:session',
            description='Camper-specific session', time_label='10 AM',
            start_time=time(10), end_time=time(11), display_order=1,
            modified_by=self.owner)
        audio = LectureRecording.objects.create(
            edition=self.edition, session=private_session,
            title='Restricted audio', audio='camp-recordings/private.mp3')
        audio.state = 'published'
        audio.save(actor=self.operator)
        asset_id = self.post('studio-assets', {
            'source_kind': 'recordings', 'source_id': audio.pk}).json()['asset']['id']
        denied = self.post('studio-placements', {
            'destination': 'foundation_archive', 'action': 'publish'}, args=[asset_id])
        self.assertEqual(denied.status_code, 400, denied.content)
        allowed = self.post('studio-placements', {
            'destination': 'camper_resources', 'edition': self.edition.pk,
            'action': 'publish'}, args=[asset_id])
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(Client().get(reverse('dic:studio-public-audio', args=[asset_id])).status_code, 404)
        self.assertEqual(Client().get(reverse('dic:studio-public-placements'),
                           {'destination': 'foundation_archive'}).json()['items'], [])

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

    def test_gallery_filtering_searches_all_pages_and_never_leaks_unapproved_collections(self):
        for n in range(36):
            StudioAsset.objects.create(
                source_kind='photos', source_id=20000 + n,
                title=f'Gallery photo {n}', album='Event gallery' if n % 2 else 'Camp moments',
                created_by=self.owner)
        StudioAsset.objects.create(source_kind='recordings', source_id=30001,
                                   title='Private audio fixture', created_by=self.owner)
        url = reverse('dic:studio-assets')
        photos = self.client.get(url, {'kind': 'photos', 'album': 'Event gallery', 'q': 'Gallery'})
        self.assertEqual(photos.status_code, 200, photos.content)
        self.assertEqual(len(photos.json()['assets']), 18)
        self.assertEqual({x['album'] for x in photos.json()['assets']}, {'Event gallery'})
        self.assertEqual(set(photos.json()['albums']), {'Camp moments', 'Event gallery'})
        self.assertFalse(photos.json()['has_more'])
        self.assertEqual(self.client.get(url, {'kind': 'recordings', 'album': 'Event gallery'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'q': 'x' * 101}).status_code, 400)
        viewer = get_user_model().objects.create_user(
            'gallery-viewer', password='synthetic', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_campphotograph'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(url, {'kind': 'recordings'}).status_code, 403)
        self.assertEqual(self.client.get(url, {'kind': 'photos'}).status_code, 403)

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
            # A staff-authorized, ID-based preview route is intentional.
            # The response must never reveal a private storage object name,
            # credential, presigned key or bucket endpoint.
            self.assertEqual(len(page_one.json()['items']), 30)
            self.assertTrue(all(item['preview_url'].startswith('/api/v1/dic/memories/')
                                and item['preview_url'].endswith('/image/?preview=1')
                                for item in page_one.json()['items']))
            stored_name = CampPhotograph.objects.first().photograph.name
            self.assertNotIn(stored_name, page_one.content.decode())
            self.assertNotIn('r2.cloudflarestorage.com', page_one.content.decode())
            anonymous = Client()
            preview = page_one.json()['items'][0]['preview_url']
            self.assertEqual(anonymous.get(preview).status_code, 404)
            self.assertEqual(self.client.get(preview).status_code, 200)
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


    def test_media_personnel_can_delete_never_published_draft_with_audit(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo('Remove this unused synthetic draft')
            asset = self.post('studio-assets', {
                'source_kind': 'photos', 'source_id': photo.pk})
            self.assertEqual(asset.status_code, 201)
            photo_id = photo.pk
            result = self.client.delete(
                reverse('dic:studio-draft-delete', args=['photos', photo_id]),
                HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(result.status_code, 200, result.content)
            self.assertFalse(CampPhotograph.objects.filter(pk=photo_id).exists())
            self.assertFalse(StudioAsset.objects.filter(
                source_kind='photos', source_id=photo_id).exists())
            self.assertTrue(DICAdminAuditEvent.objects.filter(
                action='studio_media_draft_deleted', target_id=str(photo_id)).exists())

    def test_owner_can_remove_withdrawn_unplaced_draft_preserving_audit(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo('Temporary withdrawn test')
            key = str(photo.pk)
            url = reverse('dic:studio-draft-delete', args=['photos', photo.pk])
            DICAdminAuditEvent.objects.create(
                actor=self.operator, action='studio_media_publish',
                target_type='CampPhotograph', target_id=key,
                details={'library': 'photos'})
            DICAdminAuditEvent.objects.create(
                actor=self.operator, action='studio_media_withdraw',
                target_type='CampPhotograph', target_id=key,
                details={'library': 'photos'})
            self.client.force_login(self.owner)
            csrf = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
            unconfirmed = self.client.delete(
                url, data='{"confirm_historical_deletion": false}',
                content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(unconfirmed.status_code, 400)
            self.assertTrue(CampPhotograph.objects.filter(pk=photo.pk).exists())
            confirmed = self.client.delete(
                url, data='{"confirm_historical_deletion": true}',
                content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(confirmed.status_code, 200, confirmed.content)
            self.assertFalse(CampPhotograph.objects.filter(pk=photo.pk).exists())
            self.assertTrue(DICAdminAuditEvent.objects.filter(
                action='studio_media_publish', target_type='CampPhotograph', target_id=key).exists())
            self.assertTrue(DICAdminAuditEvent.objects.filter(
                action='studio_media_withdraw', target_type='CampPhotograph', target_id=key).exists())
            self.assertTrue(DICAdminAuditEvent.objects.filter(
                action='studio_media_draft_deleted', target_type='CampPhotograph',
                target_id=key, details__previously_published=True).exists())

    def test_owner_cannot_delete_historical_item_with_placement(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo('Official retained asset')
            asset_id = self.post('studio-assets', {
                'source_kind': 'photos', 'source_id': photo.pk}).json()['asset']['id']
            self.post('studio-placements', {
                'destination': 'foundation_archive', 'action': 'draft'}, args=[asset_id])
            self.client.force_login(self.owner)
            csrf = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']
            denied = self.client.delete(
                reverse('dic:studio-draft-delete', args=['photos', photo.pk]),
                data='{"confirm_historical_deletion": true}',
                content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(denied.status_code, 400, denied.content)
            self.assertTrue(CampPhotograph.objects.filter(pk=photo.pk).exists())

    def test_draft_deletion_refuses_placements_published_history_and_foreign_actors(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo('Protected draft')
            url = reverse('dic:studio-draft-delete', args=['photos', photo.pk])
            linked = self.post('studio-assets', {
                'source_kind': 'photos', 'source_id': photo.pk})
            self.assertEqual(linked.status_code, 201)
            asset_id = linked.json()['asset']['id']
            placement = self.post('studio-placements', {
                'destination': 'foundation_home', 'action': 'draft'}, args=[asset_id])
            self.assertEqual(placement.status_code, 200)
            denied = self.client.delete(url, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(denied.status_code, 400, denied.content)
            self.assertTrue(CampPhotograph.objects.filter(pk=photo.pk).exists())
            StudioPlacement.objects.all().delete()
            photo.state = 'published'
            photo.save(actor=self.operator)
            photo.state = 'draft'
            photo.save(actor=self.operator)
            DICAdminAuditEvent.objects.create(
                actor=self.operator, action='studio_media_publish',
                target_type='CampPhotograph', target_id=str(photo.pk), details={})
            denied_history = self.client.delete(url, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(denied_history.status_code, 400)
            outsider = get_user_model().objects.create_user(
                'synthetic-outside-editor', password='synthetic', is_staff=True)
            self.client.force_login(outsider)
            denied_role = self.client.delete(url, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(denied_role.status_code, 403)
            self.assertTrue(CampPhotograph.objects.filter(pk=photo.pk).exists())



    def test_photo_mosaic_is_bounded_and_keeps_default_home_feed_compatible(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            ids = []
            for n in range(11):
                photo = self.photo('Mosaic photo ' + str(n))
                photo.state = 'published'
                photo.save(actor=self.operator)
                asset_id = self.post('studio-assets', {
                    'source_kind': 'photos', 'source_id': photo.pk}).json()['asset']['id']
                response = self.post('studio-placements', {
                    'destination': 'foundation_home', 'action': 'publish'}, args=[asset_id])
                self.assertEqual(response.status_code, 200, response.content)
                ids.append(asset_id)
            url = reverse('dic:studio-public-placements')
            anonymous = Client()
            params = {'destination': 'foundation_home', 'view': 'photos'}
            feed = anonymous.get(url, params).json()
            self.assertEqual(len(feed['items']), 9)
            self.assertFalse(feed['has_more'])
            self.assertEqual(len({row['url'] for row in feed['items']}), 9)
            self.assertTrue(all(row['source_kind'] == 'photos' and row['alt_text']
                                for row in feed['items']))
            self.assertEqual(anonymous.get(url, {**params, 'page': 2}).json()['items'], [])
            self.assertEqual(len(anonymous.get(url, {'destination': 'foundation_home'}).json()['items']), 3)
            self.assertEqual(anonymous.get(url, {'destination': 'foundation_home',
                                                'view': 'editorial'}).json()['items'], [])
            self.post('studio-placements', {'destination': 'foundation_home',
                      'action': 'withdraw'}, args=[ids[-1]])
            updated = anonymous.get(url, params).json()['items']
            self.assertEqual(len(updated), 9)
            self.assertNotIn(feed['items'][0]['url'], [row['url'] for row in updated])
            self.assertEqual(anonymous.get(url, {'destination': 'camper_resources',
                                                'view': 'photos'}).status_code, 404)

    def test_camp_mosaic_preserves_legacy_featured_photos_but_respects_withdrawal(self):
        with TemporaryDirectory() as root, override_settings(
            DEBUG=True, DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=root):
            photo = self.photo('Legacy featured photograph')
            photo.featured = True
            photo.state = 'published'
            photo.save(actor=self.operator)
            draft = self.photo('Unpublished photograph')
            draft.featured = True
            draft.save()
            url = reverse('dic:studio-public-placements')
            params = {'destination': 'dic_memories', 'view': 'photos'}
            anonymous = Client()
            feed = anonymous.get(url, params).json()['items']
            self.assertEqual(len(feed), 1)
            self.assertEqual(feed[0]['title'], photo.caption)
            asset_id = self.post('studio-assets', {'source_kind': 'photos',
                         'source_id': photo.pk}).json()['asset']['id']
            self.assertEqual(anonymous.get(url, params).json()['items'], [])
            placement = {'destination': 'dic_memories', 'edition': self.edition.pk}
            response = self.post('studio-placements', {**placement, 'action': 'publish'}, args=[asset_id])
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(len(anonymous.get(url, params).json()['items']), 1)
            self.post('studio-placements', {**placement, 'action': 'withdraw'}, args=[asset_id])
            self.assertEqual(anonymous.get(url, params).json()['items'], [])
