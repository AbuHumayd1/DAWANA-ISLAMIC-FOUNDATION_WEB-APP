"""Regression checks for deduplicated DIC flyer placements."""
from importlib import import_module
from uuid import UUID
from django.apps import apps
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

    def test_one_time_cleanup_targets_only_verified_original_asset(self):
        verified_id = UUID('4613b779-5f1a-4a4d-976e-e9fbf1dca914')
        verified = StudioAsset.objects.create(
            id=verified_id, source_kind='flyers', source_id=1, title="DIC'26 FLYER")
        other = StudioAsset.objects.create(
            source_kind='flyers', source_id=2, title='Unrelated flyer')
        # The migration is intentionally edition-id scoped; create a separate
        # matching edition only if this synthetic database has id=1.
        target = StudioPlacement.objects.create(
            asset=verified, edition=self.edition,
            destination='dic_landing', state='published')
        other_placement = StudioPlacement.objects.create(
            asset=other, edition=self.edition,
            destination='dic_landing', state='published')
        migration = import_module('dic.migrations.0046_withdraw_duplicate_dic2026_flyer_placement')
        migration.withdraw_verified_duplicate(apps, None)
        target.refresh_from_db()
        other_placement.refresh_from_db()
        if self.edition.pk == 1:
            self.assertEqual(target.state, 'withdrawn')
        else:
            self.assertEqual(target.state, 'published')
        self.assertEqual(other_placement.state, 'published')
        self.assertIsNone(verified.archived_at)
