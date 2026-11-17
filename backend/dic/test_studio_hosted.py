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

    def test_bad_url_rejects_entire_batch_without_creating_media(self):
        response = self.submit('studio-hosted-links', {'items': [
            {'title': 'Acceptable', 'video_url': 'https://youtu.be/abcDEFG1234'},
            {'title': 'Blocked', 'video_url': 'https://video.example.test/live/abcDEFG1234'},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudioHostedVideo.objects.count(), 0)
        self.assertEqual(StudioAsset.objects.count(), 0)

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
