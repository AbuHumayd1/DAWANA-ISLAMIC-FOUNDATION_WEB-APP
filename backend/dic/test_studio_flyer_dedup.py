"""Regression checks for deduplicated DIC flyer placements."""
from django.test import TestCase
from django.urls import reverse
from dic.models import CampEdition
from dic.studio_models import StudioAsset, StudioPlacement


class OfficialFlyerPlacementTests(TestCase):
    def setUp(self):
        from datetime import date
        self.edition = CampEdition.objects.create(
            name='Synthetic 2038', year=2038,
            camp_start_date=date(2038, 12, 23),
            camp_end_date=date(2039, 1, 1), is_active=True,
        )

    def test_dic_landing_omits_flyers_but_does_not_modify_source_publication(self):
        flyer = StudioAsset.objects.create(
            source_kind='flyers', source_id=1, title='Synthetic flyer')
        placement = StudioPlacement.objects.create(
            asset=flyer, edition=self.edition,
            destination='dic_landing', state='published',
        )
        response = self.client.get(reverse('dic:studio-public-placements'),
                                   {'destination': 'dic_landing'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])
        placement.refresh_from_db()
        self.assertEqual(placement.state, 'published')
        self.assertIsNone(flyer.archived_at)

