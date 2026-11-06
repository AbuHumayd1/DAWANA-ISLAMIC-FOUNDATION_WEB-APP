"""Mocked provider and catalog tests; no credentials, buckets or database access."""
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import SimpleTestCase, override_settings
from PIL import Image
from .memory_storage import PrivateMemoryStorage, PrivateParticipantStorage
from .object_lifecycle import delete_unreferenced_object
from .storage_configuration import production_storage


CONFIG = {'DIC_PRODUCTION_STORAGE': True, 'DIC_MEMORY_STORAGE': 's3', 'DEBUG': False}
for kind, bucket in [('MEDIA', 'dawana-production-media'), ('PRIVATE', 'dawana-production-private')]:
    CONFIG.update({f'DIC_{kind}_S3_BUCKET': bucket,
        f'DIC_{kind}_S3_ENDPOINT': 'https://' + '0'*32 + '.r2.cloudflarestorage.com',
        f'DIC_{kind}_S3_REGION': 'auto', f'DIC_{kind}_S3_ACCESS_KEY_ID': 'synthetic-'+kind,
        f'DIC_{kind}_S3_SECRET_ACCESS_KEY': 'synthetic-secret-'+kind})


def photo():
    data = BytesIO()
    Image.new('RGB', (4, 4)).save(data, 'PNG')
    return SimpleUploadedFile('input.png', data.getvalue(), content_type='image/png')


@override_settings(**CONFIG)
class ProductionStorageTests(SimpleTestCase):
    def test_editorial_and_portrait_buckets_are_independent(self):
        self.assertEqual(PrivateMemoryStorage()._bucket(), 'dawana-production-media')
        self.assertEqual(PrivateParticipantStorage()._bucket(), 'dawana-production-private')
        with patch('boto3.client') as client:
            PrivateParticipantStorage()._client()
            self.assertEqual(client.call_args.kwargs['aws_access_key_id'], 'synthetic-PRIVATE')

    def test_missing_private_config_never_uses_editorial_or_staging(self):
        for suffix, invalid in [('S3_BUCKET', 'dawana-staging-media'), ('S3_BUCKET', ''),
                ('S3_ENDPOINT', 'http://unsafe.invalid'), ('S3_REGION', 'us-east-1'), ('S3_ACCESS_KEY_ID', '')]:
            with self.subTest(suffix=suffix), self.settings(**{'DIC_PRIVATE_'+suffix: invalid}):
                with patch('boto3.client') as client:
                    with self.assertRaises(ImproperlyConfigured): PrivateParticipantStorage()._client()
                    client.assert_not_called()

    @override_settings(DIC_PRODUCTION_STORAGE=False, DIC_MEMORY_S3_BUCKET='dawana-staging-media',
        DIC_MEMORY_S3_ENDPOINT='https://staging.example.test', DIC_MEMORY_S3_REGION='auto')
    def test_legacy_staging_stays_on_its_existing_bucket_and_credential_chain(self):
        for storage in (PrivateMemoryStorage(), PrivateParticipantStorage()):
            self.assertEqual(storage._bucket(), 'dawana-staging-media')
            with patch('boto3.client') as client:
                storage._client()
                self.assertNotIn('aws_access_key_id', client.call_args.kwargs)

    def test_verified_replacement_upload_uses_new_key_and_never_deletes_old(self):
        storage, client = PrivateParticipantStorage(), Mock()
        client.head_object.side_effect = lambda **kw: {'ContentLength': len(client.put_object.call_args.kwargs['Body'])}
        with patch.object(storage, '_client', return_value=client):
            name = storage.save('old.jpg', photo())
        self.assertTrue(name.startswith('participants/portraits/'))
        self.assertEqual(client.put_object.call_args.kwargs['IfNoneMatch'], '*')
        client.delete_object.assert_not_called()

    def test_upload_or_verification_failure_never_deletes_previous_object(self):
        for upload_failure in (True, False):
            storage, client = PrivateParticipantStorage(), Mock()
            if upload_failure: client.put_object.side_effect = OSError('synthetic failure')
            else: client.head_object.return_value = {'ContentLength': -1}
            with patch.object(storage, '_client', return_value=client):
                with self.assertRaises((OSError, ValidationError)): storage.save('old.jpg', photo())
            client.delete_object.assert_not_called()

    def test_failed_record_save_retains_previous_object_and_default_delete_is_denied(self):
        from .models import CampEnrollment
        enrollment = CampEnrollment()
        enrollment.portrait.name = 'previous.jpg'
        storage = enrollment.portrait.storage
        with patch.object(storage, 'save', return_value='participants/portraits/new.jpg'), \
                patch.object(enrollment, 'save', side_effect=RuntimeError('synthetic database failure')), \
                patch.object(storage, 'delete') as delete:
            with self.assertRaises(RuntimeError): enrollment.portrait.save('new.jpg', photo())
            delete.assert_not_called()
        with self.assertRaises(ValidationError): storage.delete('previous.jpg')

    def test_explicit_delete_rejects_references_and_deletes_only_unreferenced_key(self):
        storage, client = PrivateParticipantStorage(), Mock()
        field = models.FileField(storage=storage)
        field.set_attributes_from_name('portrait')
        model = NS(_meta=NS(fields=[field], db_table='synthetic_files'), _base_manager=Mock())
        connection = Mock(vendor='postgresql')
        connection.ops.quote_name.side_effect = lambda name: '"'+name+'"'
        name = 'participants/portraits/'+'1'*32+'.jpg'
        with patch('dic.object_lifecycle.apps.get_models', return_value=[model]), \
                patch('dic.object_lifecycle.connection', connection), \
                patch('dic.object_lifecycle.transaction.atomic', return_value=nullcontext()), \
                patch.object(storage, '_client', return_value=client):
            model._base_manager.filter.return_value.exists.return_value = True
            with self.assertRaises(ValidationError): delete_unreferenced_object(storage, name, approved=True)
            client.delete_object.assert_not_called()
        with patch('dic.object_lifecycle.apps.get_models', return_value=[model]), \
                patch('dic.object_lifecycle.connection', connection), \
                patch('dic.object_lifecycle.transaction.atomic', return_value=nullcontext()), \
                patch.object(storage, '_client', return_value=client):
            model._base_manager.filter.return_value.exists.return_value = False
            delete_unreferenced_object(storage, name, approved=True)
            client.delete_object.assert_called_once_with(Bucket='dawana-production-private', Key=name)

    @override_settings(DIC_PRODUCTION_STORAGE=False)
    def test_deletion_never_targets_staging(self):
        with self.assertRaises(ValidationError):
            delete_unreferenced_object(PrivateMemoryStorage(), 'memories/'+'1'*32+'.jpg', approved=True)


class MediaAuthorizationTests(SimpleTestCase):
    def test_anonymous_and_invalid_grants_never_open_objects_for_any_card_format(self):
        from rest_framework.exceptions import AuthenticationFailed, NotFound
        from rest_framework.test import APIRequestFactory
        from .participant_api import PortalCardView
        for format in ('pvc', 'a6', 'portrait'):
            for failure in (AuthenticationFailed('expired or revoked'), NotFound('out of scope')):
                with self.subTest(format=format, error=type(failure).__name__), \
                        patch('dic.participant_api.authorized_portal_card', side_effect=failure), \
                        patch.object(PrivateParticipantStorage, '_client') as client:
                    response = PortalCardView.as_view()(APIRequestFactory().get('/?format='+format), enrollment_id='synthetic')
                    self.assertIn(response.status_code, (403, 404))
                    client.assert_not_called()

    def test_missing_objects_and_provider_failures_are_sanitized_and_not_cacheable(self):
        from botocore.exceptions import ClientError
        from .media_delivery import safe_media
        for code, expected in [('NoSuchKey', 404), ('AccessDenied', 503)]:
            view = safe_media(Mock(side_effect=ClientError({'Error': {'Code': code, 'Message': 'private-key'}}, 'GetObject')))
            response = view()
            self.assertEqual(response.status_code, expected)
            self.assertNotIn(b'private-key', response.content)
            self.assertIn('no-store', response['Cache-Control'])
