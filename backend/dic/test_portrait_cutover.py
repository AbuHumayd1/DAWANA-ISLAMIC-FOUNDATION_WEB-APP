"""Mocked copy/inventory contracts: no database, credential or provider access."""
from io import BytesIO
from unittest.mock import Mock
from botocore.exceptions import ClientError
from django.test import SimpleTestCase
from .portrait_cutover import portrait_inventory, copy_portraits, CutoverStopped, DESTINATION


def result(data):
    return {'Body': BytesIO(data), 'ContentLength': len(data)}


class PortraitCutoverTests(SimpleTestCase):
    def setUp(self):
        self.key = 'memories/' + 'a' * 32 + '.jpg'
        self.inventory = portrait_inventory([self.key, self.key, ''])
        self.source, self.destination = Mock(), Mock()
        self.data = b'synthetic-image-bytes'
        self.source.head_object.return_value = {'ContentLength': len(self.data), 'ETag': 'source-version'}
        self.source.get_object.side_effect = lambda **kwargs: result(self.data)
        self.destination.head_object.return_value = {'ContentLength': len(self.data)}
        self.missing = ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')

    def copy(self, **kwargs):
        return copy_portraits(self.inventory, self.source, self.destination,
            source_bucket='owner-confirmed-legacy-bucket', destination_bucket=DESTINATION,
            maintenance_approved=True, writers_suspended=True, **kwargs)

    def test_exact_keys_and_shared_reference_counts_are_preserved(self):
        self.assertEqual(self.inventory, [{'key': self.key, 'references': 2}])
        self.destination.get_object.side_effect = [self.missing, result(self.data)]
        report = self.copy()
        self.assertEqual(self.destination.put_object.call_args.kwargs['Key'], self.key)
        self.assertEqual(self.destination.put_object.call_args.kwargs['IfNoneMatch'], '*')
        self.assertEqual(report[0]['status'], 'copied_verified')
        self.assertNotIn(self.key, str(report))
        self.source.delete_object.assert_not_called()
        self.destination.delete_object.assert_not_called()

    def test_missing_source_stops_before_destination_access(self):
        self.source.head_object.side_effect = self.missing
        with self.assertRaises(CutoverStopped): self.copy()
        self.assertEqual(self.destination.mock_calls, [])

    def test_failed_copy_stops_and_never_deletes(self):
        self.destination.get_object.side_effect = self.missing
        self.destination.put_object.side_effect = OSError('sensitive-provider-detail')
        with self.assertRaises(CutoverStopped) as failure: self.copy()
        self.assertNotIn('sensitive-provider-detail', str(failure.exception.report))
        self.source.delete_object.assert_not_called()

    def test_size_and_checksum_mismatches_stop(self):
        for invalid in (b'x', b'X' * len(self.data)):
            with self.subTest(size=len(invalid)):
                self.destination.get_object.side_effect = [self.missing, result(invalid)]
                with self.assertRaises(CutoverStopped) as failure: self.copy()
                self.assertIn(failure.exception.report[-1]['reason'], ('size_mismatch', 'checksum_mismatch'))

    def test_conflicting_destination_is_never_overwritten(self):
        self.destination.get_object.side_effect = lambda **kwargs: result(b'conflicting')
        with self.assertRaises(CutoverStopped) as failure: self.copy()
        self.assertEqual(failure.exception.report[-1]['reason'], 'destination_conflict')
        self.destination.put_object.assert_not_called()

    def test_rerun_verifies_identical_existing_object_without_writing(self):
        self.destination.get_object.side_effect = lambda **kwargs: result(self.data)
        self.assertEqual(self.copy()[0]['status'], 'verified_existing')
        self.assertEqual(self.copy()[0]['status'], 'verified_existing')
        self.destination.put_object.assert_not_called()

    def test_provider_checksum_mismatch_stops(self):
        self.source.get_object.side_effect = lambda **kwargs: {
            **result(self.data), 'ChecksumSHA256': 'invalid', 'ChecksumType': 'FULL_OBJECT'}
        with self.assertRaises(CutoverStopped): self.copy()
        self.destination.put_object.assert_not_called()

    def test_maintenance_is_required_before_any_provider_call(self):
        with self.assertRaises(ValueError):
            copy_portraits(self.inventory, self.source, self.destination,
                source_bucket='owner-confirmed-legacy-bucket', destination_bucket=DESTINATION)
        self.assertEqual(self.source.mock_calls, [])
