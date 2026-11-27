from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class StudioVideoTransferTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('transfer-test', is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='dic', codename__in=['view_campvideo','add_campvideo']))
        self.client.force_login(self.user)
        self.url = reverse('dic:studio-video-transfer')

    @patch('dic.studio_video_upload.upload_enabled', return_value=True)
    @patch('dic.studio_video_upload.recording_storage._bucket', return_value='synthetic')
    @patch('dic.studio_video_upload.recording_storage._client')
    def test_signed_parts_and_limits(self, storage, bucket, enabled):
        storage.return_value.create_multipart_upload.return_value = {'UploadId':'synthetic'}
        storage.return_value.generate_presigned_url.return_value = 'https://example.invalid/part'
        def post(data):
            return self.client.post(self.url, data, content_type='application/json')
        self.assertEqual(post({'action':'start','name':'video.mp4','size':201*1024*1024}).status_code,400)
        start = post({'action':'start','name':'video.mp4','size':1024})
        self.assertEqual(start.status_code,200,start.content)
        ticket=start.json()['ticket']
        self.assertEqual(post({'action':'part','ticket':ticket,'number':2}).status_code,400)
        self.assertEqual(post({'action':'part','ticket':ticket,'number':1}).status_code,200)
        self.assertEqual(post({'action':'part','ticket':ticket+'x','number':1}).status_code,400)
        outsider=get_user_model().objects.create_user('transfer-outsider',is_staff=True)
        outsider.user_permissions.add(*self.user.user_permissions.all())
        self.client.force_login(outsider)
        self.assertEqual(post({'action':'part','ticket':ticket,'number':1}).status_code,400)
