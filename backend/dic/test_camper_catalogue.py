"""Database-free projection regression. No provider, credentials or award writes."""
from unittest.mock import patch
from django.test import SimpleTestCase
from .camper_catalogue import camper_catalogue


class CamperCatalogueTests(SimpleTestCase):
    def test_real_approved_policy_has_exact_counts_and_only_safe_fields(self):
        data = camper_catalogue(2026, True)
        self.assertTrue(data['ready'])
        self.assertEqual(len(data['activities']), 55)
        self.assertEqual(sum(row['kind'] == 'individual' for row in data['activities']), 38)
        for row in data['activities']:
            self.assertEqual(set(row), {'code','name','kind','category','points','frequency','mode','threshold'})
            self.assertIsInstance(row['points'], int)

    def test_wrong_edition_or_missing_storage_never_reads_policy(self):
        with patch('dic.camper_catalogue.catalogue_options') as policy:
            for year, ready in ((2025, True), (2026, False), (2098, True)):
                self.assertFalse(camper_catalogue(year, ready)['ready'])
                self.assertEqual(camper_catalogue(year, ready)['activities'], [])
            policy.assert_not_called()

    def test_unapproved_policy_is_not_exposed(self):
        with patch('dic.camper_catalogue.catalogue_options', return_value={'ready': False}):
            self.assertEqual(camper_catalogue(2026, True)['activities'], [])

    def test_private_or_extra_policy_fields_are_not_forwarded(self):
        row = dict(code='SYNTHETIC',name='Synthetic test only',kind='individual',category='Test',
                   points=3,frequency='daily',mode='verified',threshold=None,
                   participant='PRIVATE',evidence='PRIVATE',published=False)
        with patch('dic.camper_catalogue.catalogue_options',return_value=dict(ready=True,individual=[row],collective=[])):
            result = camper_catalogue(2026,True)
        self.assertNotIn('PRIVATE', str(result))
        self.assertNotIn('published', result['activities'][0])
