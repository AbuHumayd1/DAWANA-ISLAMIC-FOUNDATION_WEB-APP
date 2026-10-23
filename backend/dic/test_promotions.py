"""No provider calls: publication/privacy and range delivery regression checks."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TransactionTestCase, RequestFactory, override_settings
from django.urls import reverse
from .models import CampEdition
from .promo_models import PromoVideo, CampFlyer
from .promo_views import parse_range, promo_stream
from .test_allocation import AllocationFixtures


class RangeTests(SimpleTestCase):
    def test_browser_ranges_and_invalid_requests(self):
        self.assertEqual(parse_range(None, 100), (0, 99, False))
        self.assertEqual(parse_range('bytes=10-19', 100), (10, 19, True))
        self.assertEqual(parse_range('bytes=50-', 100), (50, 99, True))
        self.assertEqual(parse_range('bytes=-10', 100), (90, 99, True))
        self.assertEqual(parse_range('bytes=0-999', 100), (0, 99, True))
        for value in ('bytes=100-', 'bytes=-0', 'bytes=3-2', 'bytes=0-1,5-6', 'bytes=-', 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_range(value, 100)

    @override_settings(DIC_MEMORY_S3_BUCKET='synthetic-bucket')
    @patch('dic.promo_views.asset')
    def test_remote_stream_is_bounded_and_closes_body(self, asset):
        storage = Mock()
        storage._backend.return_value = None
        client = storage._client.return_value
        client.head_object.return_value = {'ContentLength': 100}
        body = BytesIO(b'0123456789')
        client.get_object.return_value = {'Body': body}
        asset.return_value.video = SimpleNamespace(storage=storage, name='memories/promos/synthetic.mp4')
        request = RequestFactory().get('/', HTTP_RANGE='bytes=10-19')
        response = promo_stream(request, 1)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 10-19/100')
        self.assertEqual(b''.join(response.streaming_content), b'0123456789')
        self.assertTrue(body.closed)
        client.get_object.assert_called_once_with(Bucket='synthetic-bucket', Key='memories/promos/synthetic.mp4', Range='bytes=10-19')
        response.close()

    @patch('dic.promo_views.asset')
    def test_head_and_unsatisfiable_ranges_do_not_fetch_video(self, asset):
        storage = Mock()
        storage._backend.return_value = None
        client = storage._client.return_value
        client.head_object.return_value = {'ContentLength': 100}
        asset.return_value.video = SimpleNamespace(storage=storage, name='synthetic')
        for request, expected in [(RequestFactory().head('/'), 200), (RequestFactory().get('/', HTTP_RANGE='bytes=100-'), 416)]:
            self.assertEqual(promo_stream(request, 1).status_code, expected)
        client.get_object.assert_not_called()


class EditorialPublicationTests(AllocationFixtures, TransactionTestCase):
    def setUp(self):
        self.edition = self.make_edition(year=2026)
        CampEdition.objects.filter(pk=self.edition.pk).update(is_active=True)
        self.previous = self.make_edition(year=2025)
        self.publisher = get_user_model().objects.create_superuser(username='synthetic-publisher', email='publisher@example.test', password='synthetic-only')

    def video(self, **changes):
        fields = dict(edition=self.edition, source_edition=self.previous, kind='experience', title='Synthetic clip', description='Synthetic test only', video='memories/promos/synthetic.mp4', poster='memories/synthetic.jpg', alt_text='Synthetic poster')
        fields.update(changes)
        obj = PromoVideo(**fields)
        obj.save()
        return obj

    def test_draft_metadata_and_assets_are_private(self):
        obj = self.video()
        self.assertEqual(self.client.get(reverse('dic:dic-editorial')).json()['experiences'], [])
        for route in ('promo-stream', 'promo-poster'):
            self.assertEqual(self.client.get(reverse(f'dic:{route}', args=[obj.pk])).status_code, 404)
            self.assertEqual(self.client.get(reverse(f'dic:{route}', args=[obj.pk]) + '?preview=1').status_code, 404)

    def test_publishing_permission_caps_and_withdrawal(self):
        first = self.video()
        first.state = 'published'
        with self.assertRaises(PermissionDenied):
            first.save()
        first.save(actor=self.publisher)
        for _ in range(2):
            obj = self.video()
            obj.state = 'published'
            obj.save(actor=self.publisher)
        fourth = self.video()
        fourth.state = 'published'
        with self.assertRaises(ValidationError):
            fourth.save(actor=self.publisher)
        self.assertEqual(len(self.client.get(reverse('dic:dic-editorial')).json()['experiences']), 3)
        first.state = 'draft'
        first.save(actor=self.publisher)
        self.assertEqual(self.client.get(reverse('dic:promo-stream', args=[first.pk])).status_code, 404)
        self.assertEqual(len(self.client.get(reverse('dic:dic-editorial')).json()['experiences']), 2)

    def test_introductions_are_limited_to_two(self):
        for _ in range(2):
            obj = self.video(kind='introduction', source_edition=None)
            obj.state = 'published'
            obj.save(actor=self.publisher)
        obj = self.video(kind='introduction', source_edition=None)
        obj.state = 'published'
        with self.assertRaises(ValidationError):
            obj.save(actor=self.publisher)

    def test_flyer_draft_is_not_disclosed(self):
        flyer = CampFlyer(edition=self.edition, title='Synthetic flyer', image='memories/synthetic.jpg', alt_text='Synthetic flyer')
        flyer.save()
        self.assertIsNone(self.client.get(reverse('dic:dic-editorial')).json()['flyer'])
        self.assertEqual(self.client.get(reverse('dic:official-flyer', args=[flyer.pk])).status_code, 404)

class MP4ValidationTests(SimpleTestCase):
    @patch('dic.promo_storage.shutil.which', return_value='/synthetic/ffprobe')
    @patch('dic.promo_storage.subprocess.run')
    def test_validator_checks_real_container_and_compatible_streams(self, run, executable):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .promo_storage import validate_mp4
        run.return_value.stdout = b'{"streams":[{"codec_type":"video","codec_name":"h264"},{"codec_type":"audio","codec_name":"aac"}],"format":{"duration":"30"}}'
        upload = SimpleUploadedFile('synthetic.mp4', b'\x00\x00\x00\x18ftypisom' + b'synthetic-only')
        validate_mp4(upload)
        self.assertEqual(upload.tell(), 0)
        self.assertIn('-protocol_whitelist', run.call_args.args[0])
        self.assertIn('-enable_drefs', run.call_args.args[0])
        run.return_value.stdout = b'{"streams":[{"codec_type":"video","codec_name":"h264"}],"format":{"duration":"181"}}'
        with self.assertRaises(ValidationError):
            validate_mp4(upload)
        with self.assertRaises(ValidationError):
            validate_mp4(SimpleUploadedFile('fake.mp4', b'<script>not a video</script>'))

    @override_settings(DIC_MEMORY_STORAGE='s3', DIC_MEMORY_S3_BUCKET='synthetic-private-bucket')
    @patch('dic.promo_storage.validate_mp4')
    def test_storage_uses_create_only_mp4_without_changing_image_storage(self, validate):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .promo_storage import PrivatePromoStorage
        storage = PrivatePromoStorage()
        client = Mock()
        with patch.object(storage, '_client', return_value=client):
            key = storage.save('original-name.mp4', SimpleUploadedFile('original-name.mp4', b'synthetic-only'))
        payload = client.put_object.call_args.kwargs
        self.assertRegex(key, r'^memories/promos/[a-f0-9]{32}\.mp4$')
        self.assertEqual(payload['IfNoneMatch'], '*')
        self.assertEqual(payload['ContentType'], 'video/mp4')
        self.assertNotIn('ACL', payload)
