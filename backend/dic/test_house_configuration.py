"""Database-free coverage for the final approved 2026 inventory."""
from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .house_configuration import approved_2026_houses, house_capacity_limit
from .housing_policy import validate_inventory, validate_occupant
from .housing_service import check_group_house
from .allocation import AllocationError
from .models import House
from .scoring_services import combined_leaderboard


class FinalHouseConfigurationTests(SimpleTestCase):
    def edition(self, year=2026):
        return NS(pk=1, year=year, housing_age_reference_date=date(2026,12,23))

    def house(self, gender='male', capacity=30):
        return NS(pk=1, edition_id=1, name='Configured', gender=gender, purpose='participants',
            capacity=capacity, status='active', eligibility_rules={}, reserve_authorized_at=None)

    def test_exact_eight_names_colours_genders_capacity_and_metadata(self):
        rows = approved_2026_houses()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(row['capacity'] for row in rows), 240)
        self.assertEqual(sum(row['gender']=='male' for row in rows), 4)
        self.assertEqual(sum(row['gender']=='female' for row in rows), 4)
        self.assertEqual({row['badge_colour'] for row in rows}, {'#147D64','#244B91','#B46B19','#743B94','#B83F75','#168A9C','#A53E46','#677D29'})
        self.assertTrue(all(row['arabic_name'] and row['motto'] and row['status']=='active' and row['purpose']=='participants' for row in rows))
        self.assertEqual(rows[0]['name'], 'ʿUkkāshah ibn Miḥṣan')
        self.assertEqual(rows[-1]['name'], 'Al-Shifāʾ bint ʿAbdullāh')

    def test_limit_is_edition_specific(self):
        self.assertEqual(house_capacity_limit(self.edition()), 30)
        self.assertEqual(house_capacity_limit(self.edition(2027)), 25)

    def test_model_accepts_30_and_rejects_31_without_saving(self):
        from .models import CampEdition
        edition = CampEdition(pk=1, year=2026)
        house = House(edition=edition, name='Configured', gender='male', capacity=30)
        house.clean()
        house.capacity = 31
        with self.assertRaises(ValidationError):
            house.clean()
        edition.year = 2027; house.capacity = 30
        with self.assertRaises(ValidationError):
            house.clean()

    def test_2026_inventory_accepts_eight_without_reserves(self):
        edition = self.edition()
        houses = [NS(**{**row, 'pk': index, 'eligibility_rules': {}}) for index,row in enumerate(approved_2026_houses(),1)]
        with patch('dic.models.House.objects') as manager, patch('dic.models.HouseAllocation.objects') as allocations, patch('dic.allocation.paid_participants') as paid:
            manager.filter.return_value.exclude.return_value = houses
            allocations.filter.return_value.select_related.return_value = []
            paid.return_value.values_list.return_value = []
            self.assertEqual(validate_inventory(edition), houses)

    def test_2026_rejects_extra_reserve_and_future_editions_keep_reserve_policy(self):
        houses = [NS(**{**row, 'pk': index, 'eligibility_rules': {}}) for index,row in enumerate(approved_2026_houses(),1)]
        with patch('dic.models.House.objects') as manager:
            manager.filter.return_value.exclude.return_value = houses + [self.house()]
            with self.assertRaises(ValidationError):
                validate_inventory(self.edition())
            manager.filter.return_value.exclude.return_value = houses
            with self.assertRaises(ValidationError):
                validate_inventory(self.edition(2027))

    def test_30th_member_fits_and_31st_is_rejected(self):
        member = NS(sex='Male')
        with patch('dic.housing_service.HouseAllocation.objects') as allocations:
            count = allocations.filter.return_value.exclude.return_value.count
            count.return_value = 29
            check_group_house(self.edition(), [member], self.house())
            count.return_value = 30
            with self.assertRaises(AllocationError):
                check_group_house(self.edition(), [member], self.house())

    def test_gender_and_edition_restrictions_still_apply(self):
        for house in [self.house(gender='female'), NS(**{**vars(self.house()), 'edition_id': 2})]:
            with self.assertRaises(AllocationError):
                check_group_house(self.edition(), [NS(sex='Male')], house)

    def test_direct_allocation_save_enforces_30th_and_31st_under_edition_lock(self):
        from .models import CampEdition, HouseAllocation, Participant
        edition = CampEdition(pk=1, year=2026)
        house = House(pk=1, edition=edition, capacity=30, gender='male')
        row = HouseAllocation(edition=edition, house=house, participant=Participant())
        with patch('dic.models.transaction.atomic', return_value=nullcontext()), \
             patch('dic.models.CampEdition.objects') as editions, \
             patch('dic.models.HouseAllocation.objects') as allocations, \
             patch.object(HouseAllocation, 'clean'), \
             patch('django.db.models.Model.save') as save:
            allocations.filter.return_value.count.return_value = 29
            row.save()
            editions.select_for_update.return_value.get.assert_called_with(pk=1)
            save.assert_called_once()
            allocations.filter.return_value.count.return_value = 30
            with self.assertRaises(ValidationError):
                row.save()
            save.assert_called_once()

    @patch('dic.tutor_registration.is_tutor', return_value=False)
    def test_occupant_validation_accepts_30_but_rejects_reserves_for_2026(self, is_tutor):
        participant = NS(pk=7, sex='Male', date_of_birth=date(2000,1,1), eligible_for_dedicated_accommodation=False)
        house = self.house()
        validate_occupant(participant, self.edition(), house)
        is_tutor.assert_called_once_with(participant.pk, self.edition().pk)
        house.status = 'reserve'
        with self.assertRaises(ValidationError):
            validate_occupant(participant, self.edition(), house)

    def test_all_approved_colours_and_zero_scores_reach_combined_leaderboard(self):
        houses = [NS(**{**row, 'pk': index}) for index,row in enumerate(approved_2026_houses(),1)]
        rows = combined_leaderboard(houses, [])
        self.assertEqual(len(rows),8)
        self.assertEqual({row['colour'] for row in rows}, {house.badge_colour for house in houses})
        self.assertTrue(all(row['net']==0 and row['rank']==1 for row in rows))
