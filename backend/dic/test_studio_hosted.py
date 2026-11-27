"""Link-only YouTube livestreams: no file upload, R2 dependency, or second approver."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from dic.models import CampEdition
from dic.staff_roles import ROLES
from dic.studio_hosted_models import StudioHostedVideo
from dic.studio_models import StudioAsset, StudioPlacement


@override_settings(DIC_VIDEO_APPROVED_PROVIDERS=['youtube', 'vimeo'],
                   DIC_MEDIA_STUDIO_UPLOADS_ENABLED=False,
                   DIC_MEMORY_STORAGE='disabled')
class HostedLinkPublishingTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(
            'hosted-operator', password='synthetic', is_staff=True)
        group = Group.objects.create(name='DAWANA Media Studio Personnel')
        for item in ROLES[group.name]:
            app, code = item.split('.')
            group.permissions.add(Permission.objects.get(content_type__app_label=app, codename=code))
        self.operator.groups.add(group)
        self.edition = CampEdition.objects.create(
            name='Synthetic DIC 2039', year=2039,
            camp_start_date='2039-12-23', camp_end_date='2040-01-01',
            is_active=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.operator)
        self.token = self.client.get(reverse('dic:studio-csrf')).json()['csrfToken']

    def submit(self, name, payload, args=None):
        return self.client.post(
            reverse('dic:' + name, args=args or []), payload,
            content_type='application/json', HTTP_X_CSRFTOKEN=self.token)

    def test_bulk_live_links_are_drafts_and_publish_independently(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Friday live broadcast', 'video_url': 'https://www.youtube.com/live/abcDEFG1234'},
            {'title': 'Recorded camp reminder', 'video_url': 'https://www.youtube.com/watch?v=Z1z2Z3z4Z5z',
             'edition': self.edition.pk},
        ]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(response.json()['items']), 2)
        self.assertEqual(StudioHostedVideo.objects.filter(state='draft').count(), 2)
        self.assertEqual(StudioAsset.objects.filter(source_kind='hosted').count(), 2)
        self.assertEqual(self.client.get(reverse('dic:studio-public-placements')).json()['items'], [])
        video = StudioHostedVideo.objects.get(title='Friday live broadcast')
        publish = self.submit('studio-publication', {'action': 'publish'}, ['hosted', video.pk])
        self.assertEqual(publish.status_code, 200, publish.content)
        asset = StudioAsset.objects.get(source_kind='hosted', source_id=video.pk)
        placed = self.submit('studio-placements',
                             {'destination': 'foundation_archive', 'action': 'publish'}, [asset.pk])
        self.assertEqual(placed.status_code, 200, placed.content)
        public = self.client.get(reverse('dic:studio-public-placements'),
                                 {'destination': 'foundation_archive'}).json()['items']
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]['source_kind'], 'hosted')
        self.assertEqual(public[0]['embed_url'],
                         'https://www.youtube-nocookie.com/embed/abcDEFG1234?playsinline=1')
        withdraw = self.submit('studio-placements',
                               {'destination': 'foundation_archive', 'action': 'withdraw'}, [asset.pk])
        self.assertEqual(withdraw.status_code, 200)
        self.assertEqual(self.client.get(reverse('dic:studio-public-placements')).json()['items'], [])

    def test_disabling_hosted_provider_hides_previous_public_embed_without_500(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Retired stream', 'video_url': 'https://youtu.be/abcDEFG1234'},
        ]})
        self.assertEqual(response.status_code, 201, response.content)
        video_id = response.json()['items'][0]['id']
        asset_id = response.json()['items'][0]['asset_id']
        self.assertEqual(self.submit('studio-publication', {'action': 'publish'},
                                     ['hosted', video_id]).status_code, 200)
        self.assertEqual(self.submit('studio-placements',
                                     {'destination': 'foundation_archive', 'action': 'publish'},
                                     [asset_id]).status_code, 200)
        with override_settings(DIC_VIDEO_APPROVED_PROVIDERS=[]):
            inventory = self.client.get(reverse('dic:studio-library'),
                                        {'library': 'hosted'})
            self.assertEqual(inventory.status_code, 200)
            self.assertIsNone(inventory.json()['items'][0]['player_url'])
            public = self.client.get(reverse('dic:studio-public-placements'),
                                     {'destination': 'foundation_archive'})
            self.assertEqual(public.status_code, 200)
            self.assertEqual(public.json()['items'], [])

    def test_bad_url_rejects_entire_batch_without_creating_media(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Acceptable', 'video_url': 'https://youtu.be/abcDEFG1234'},
            {'title': 'Blocked', 'video_url': 'https://video.example.test/live/abcDEFG1234'},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudioHostedVideo.objects.count(), 0)
        self.assertEqual(StudioAsset.objects.count(), 0)

    def test_provider_disabled_returns_clear_error_and_does_not_save_record(self):
        with override_settings(DIC_VIDEO_APPROVED_PROVIDERS=[]):
            status = self.client.get(reverse('dic:studio-uploads'))
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()['approved_providers'], [])
            response = self.submit('studio-hosted-links', {'items': [{
                'title': 'Test talk',
                'video_url': 'https://youtu.be/abcDEFG1234?si=testsharetoken',
            }]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Video 1', response.json()['detail'])
        self.assertIn('Video link', response.json()['detail'])
        self.assertIn('not been approved', response.json()['detail'])
        self.assertEqual(StudioHostedVideo.objects.count(), 0)

    def test_mobile_share_link_accepted_when_provider_is_enabled(self):
        status = self.client.get(reverse('dic:studio-uploads'))
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()['approved_providers'], ['youtube', 'vimeo'])
        response = self.submit('studio-hosted-links', {'items': [{
            'title': 'Shared lecture',
            'video_url': 'https://youtu.be/abcDEFG1234?si=testsharetoken',
            'lecturer': 'Example lecturer',
        }]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(StudioHostedVideo.objects.count(), 1)

    def test_public_dic_resources_show_approved_link_but_not_private_audio(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Public stream', 'video_url': 'https://youtu.be/abcDEFG1234',
             'edition': self.edition.pk},
        ]})
        self.assertEqual(response.status_code, 201, response.content)
        asset_id = response.json()['items'][0]['asset_id']
        video_id = response.json()['items'][0]['id']
        self.assertEqual(self.submit('studio-publication', {'action': 'publish'},
                                    ['hosted', video_id]).status_code, 200)
        self.assertEqual(self.submit('studio-placements', {
            'action': 'publish', 'destination': 'dic_resources', 'edition': self.edition.pk},
            [asset_id]).status_code, 200)
        items = self.client.get(reverse('dic:studio-public-placements'),
                                {'destination': 'dic_resources'}).json()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['source_kind'], 'hosted')
        self.assertNotIn('audio', str(items))

    def test_staff_library_preview_is_safe_canonical_embed_without_private_keys(self):
        created = self.submit('studio-hosted-links', {'items': [{
            'title': 'Livestream test',
            'video_url': 'https://www.youtube.com/live/abcDEFG1234',
        }]})
        self.assertEqual(created.status_code, 201, created.content)
        library = self.client.get(reverse('dic:studio-library'), {'library': 'hosted'})
        self.assertEqual(library.status_code, 200, library.content)
        self.assertEqual(library.json()['items'][0]['player_url'],
                         'https://www.youtube-nocookie.com/embed/abcDEFG1234?playsinline=1')
        self.assertNotIn('r2.cloudflarestorage.com', str(library.content))
        self.assertNotIn('secret', str(library.content))
        self.assertIsNone(library.json()['items'][0]['preview_url'])
        anonymous = Client()
        self.assertIn(anonymous.get(reverse('dic:studio-library'),
                                    {'library': 'hosted'}).status_code, (401, 403))

    def test_operator_can_publish_without_upload_switch_and_viewer_cannot_create(self):
        self.assertFalse(self.client.get(reverse('dic:studio-uploads')).json()['enabled'])
        viewer = get_user_model().objects.create_user('video-viewer', password='synthetic',
                                                      is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='dic', codename='view_studiohostedvideo'))
        self.client.force_login(viewer)
        denied = self.submit('studio-hosted-links', {'items': [
            {'title': 'Denied', 'video_url': 'https://youtu.be/abcDEFG1234'}]})
        self.assertEqual(denied.status_code, 403)


    def test_home_editorial_carousel_retains_hosted_publications_outside_photo_mosaic(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Synthetic homepage lecture', 'video_url': 'https://youtu.be/abcDEFG1234'},
        ]})
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()['items'][0]
        self.assertEqual(self.submit('studio-publication', {'action': 'publish'},
                                     ['hosted', item['id']]).status_code, 200)
        self.assertEqual(self.submit('studio-placements',
                                     {'destination': 'foundation_home', 'action': 'publish'},
                                     [item['asset_id']]).status_code, 200)
        endpoint = reverse('dic:studio-public-placements')
        public = Client()
        rows = public.get(endpoint, {'destination': 'foundation_home',
                                    'view': 'editorial'}).json()['items']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_kind'], 'hosted')
        self.assertEqual(public.get(endpoint, {'destination': 'foundation_home',
                                             'view': 'photos'}).json()['items'], [])
