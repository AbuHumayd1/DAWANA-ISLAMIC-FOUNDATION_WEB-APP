"""Database-free CP-3 policy/API/service tests. No migration or test DB needed."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from dic_scoring.models import ActivityAward
from .scoring_catalogue import catalogue, policy_ready, activity_for, RAWATIB, PRAYERS
from .activity_scoring import (award_keys, cap_check, collective_points, milestone_sources,
    verified_winner, record_activity, fingerprint, check_reversal_dependencies)
from .activity_scoring_api import ActivityInput, ActivityScoringView, CamperScoringView, ranked_people


class ActivityPolicyTests(SimpleTestCase):
    def test_exact_catalogue_values_and_counts(self):
        self.assertTrue(policy_ready())
        rows = catalogue()
        self.assertEqual(len(rows), 55)
        self.assertEqual(sum(row.kind == 'individual' for row in rows), 38)
        self.assertEqual(sum(row.kind == 'collective' for row in rows), 17)
        expected = {'SAL': [3, 2, 2, 2, 3, 5, 3], 'ADH': [3, 3, 2, 2, 5],
            'QUR': [3, 5, 5, 2, 5], 'SRV': [5, 5, 5, 3, 2, 5, 3, 3],
            'CHR': [3, 5, 5, 5, 3, 3, 5], 'MIL': [10] * 6,
            'HSP': [15, 10, 10, 10, 15, 15, 15], 'HCL': [15, 10, 15, 10, 15, 10], 'HKN': [20, 20, 20, 15]}
        for prefix, points in expected.items():
            self.assertEqual([row.points for row in rows if row.code.startswith(prefix)], points)
        self.assertEqual([row.threshold for row in rows if row.code.startswith('HSP')], ['70', '80', '80', '80', '80', '70', '80'])
        self.assertEqual(activity_for('HSP07').name, 'Class and Camp Lectures Attendance')
        self.assertFalse(any('Reading' in row.name for row in rows if row.kind == 'collective'))
        self.assertEqual(activity_for('CHR06').cap_bucket, 'character')
        self.assertTrue(all(not activity_for(f'MIL{i:02}').cap_bucket for i in range(1, 7)))

    def test_recurrence_prayers_rawatib_unique_targets_and_cross_code_exclusions(self):
        day = date(2026, 12, 20)
        for prayer in PRAYERS:
            self.assertEqual(award_keys(activity_for('SAL01'), day, prayer)[1], award_keys(activity_for('SAL02'), day, prayer)[1])
            self.assertEqual(award_keys(activity_for('SAL03'), day, prayer)[1], '')
        self.assertEqual(len({award_keys(activity_for('SAL04'), day, slot)[0] for slot in RAWATIB}), 5)
        self.assertEqual(award_keys(activity_for('ADH05'), day, 'dua-1'), award_keys(activity_for('ADH05'), day + timedelta(days=1), 'dua-1'))
        self.assertEqual(award_keys(activity_for('SRV01'), day, 'task-1')[1], award_keys(activity_for('SRV06'), day, 'task-1')[1])
        self.assertEqual(award_keys(activity_for('CHR01'), day, 'incident-1')[1], award_keys(activity_for('CHR05'), day, 'incident-1')[1])
        for code, slot in [('SAL01', 'sunrise'), ('SAL04', 'before_asr'), ('ADH05', ''), ('ADH01', 'extra')]:
            with self.assertRaises(ValidationError):
                award_keys(activity_for(code), day, slot)
        self.assertEqual(award_keys(activity_for('MIL01'), day, '')[0], 'MIL01:edition')

    def test_caps_reject_overflow_without_partial_points(self):
        cap_check('service', 5, 5)
        cap_check('character', 7, 3)
        cap_check('', 10, 10)
        for bucket in ('service', 'character'):
            with self.assertRaises(ValidationError):
                cap_check(bucket, 8, 3)

    def test_exact_threshold_exemptions_duplicates_and_zero_denominator(self):
        points, result = collective_points(activity_for('HSP01'), range(10), [], range(7))
        self.assertEqual((points, result['numerator'], result['denominator']), (15, 7, 10))
        self.assertEqual(collective_points(activity_for('HSP02'), range(6), [{'participant': 5, 'reason': 'Approved medical exemption'}], range(4))[0], 10)
        for eligible, excluded, attendees in [(range(3), [], [0, 1]), ([], [], []), ([1], [{'participant': 1, 'reason': 'approved'}], []), ([1, 2], [], [1, 1]), ([1, 2], [{'participant': 1, 'reason': 'approved'}], [1]), ([1], [{'participant': 1, 'reason': ''}], [])]:
            with self.assertRaises(ValidationError):
                collective_points(activity_for('HSP02'), eligible, excluded, attendees)

    def test_milestones_require_verified_distinct_underlying_sources(self):
        day = date(2026, 12, 20)
        def achievement(code, offset, ident, slot='', bucket=''):
            return NS(activity_code=code, activity_date=day + timedelta(days=offset), ledger_entry_id=ident, slot=slot, cap_bucket=bucket)
        self.assertEqual(milestone_sources('MIL01', [achievement('SAL06', i, i + 1) for i in range(3)]), [1, 2, 3])
        with self.assertRaises(ValidationError):
            milestone_sources('MIL01', [achievement('SAL06', i, i) for i in (0, 2, 3)])
        adhkar = [achievement(code, i, i * 2 + j) for i in range(3) for j, code in enumerate(('ADH01', 'ADH02'))]
        self.assertEqual(len(milestone_sources('MIL02', adhkar)), 6)
        with self.assertRaises(ValidationError):
            milestone_sources('MIL02', [row for row in adhkar if row.activity_code == 'ADH01'])
        self.assertEqual(len(milestone_sources('MIL03', [achievement('QUR01', i, i) for i in range(3)])), 3)
        self.assertEqual(len(milestone_sources('MIL04', [achievement('ADH05', 0, i, f'dua-{i}') for i in range(3)])), 3)
        with self.assertRaises(ValidationError):
            milestone_sources('MIL04', [achievement('ADH05', 0, i, 'same') for i in range(3)])
        self.assertEqual(milestone_sources('MIL05', [achievement('QUR05', 0, 10, 'reading-target')], 'reading-target'), [10])
        self.assertEqual(len(milestone_sources('MIL06', [achievement('SRV01', i, i, bucket='service') for i in range(3)])), 3)

    def test_verified_winners_ties_fixed_bonus_and_complete_inspection(self):
        results = [dict(house=1, marks=Decimal('90')), dict(house=2, marks=Decimal('90')), dict(house=3, marks=Decimal('80'))]
        for house in (1, 2):
            self.assertEqual(len(verified_winner(activity_for('HCL01'), house, results, [1, 2, 3])), 3)
            self.assertEqual(activity_for('HCL01').points, 15)
        with self.assertRaises(ValidationError):
            verified_winner(activity_for('HKN01'), 3, results, [1, 2, 3])
        with self.assertRaises(ValidationError):
            verified_winner(activity_for('HCL01'), 1, results[:2], [1, 2, 3])
        self.assertEqual(activity_for('HKN01').points, 20)

    def test_inputs_reject_client_points_unknown_fields_and_invalid_identifiers(self):
        payload = dict(activity='SAL01', date='2026-12-20', slot='fajr', participant=str(uuid4()), verified=True, request_id=str(uuid4()))
        self.assertTrue(ActivityInput(data=payload).is_valid())
        for extra in (dict(points=999), dict(slot='Fajr'), dict(slot='task with spaces'), dict(house=-1)):
            self.assertFalse(ActivityInput(data={**payload, **extra}).is_valid())

    def test_fingerprint_binds_actor_payload_but_not_retry_uuid(self):
        data = dict(activity='SAL01', date=date(2026, 12, 20), request_id=uuid4())
        first = fingerprint(data, NS(pk=1))
        self.assertEqual(first, fingerprint({**data, 'request_id': uuid4()}, NS(pk=1)))
        self.assertNotEqual(first, fingerprint(data, NS(pk=2)))

    def test_database_constraints_link_one_award_and_guard_claims(self):
        self.assertTrue(ActivityAward._meta.get_field('ledger_entry').one_to_one)
        names = {row.name for row in ActivityAward._meta.constraints}
        self.assertTrue({'dic_activity_individual_unique', 'dic_activity_collective_unique', 'dic_activity_exclusion_unique'} <= names)
        self.assertEqual(ActivityAward._meta.default_permissions, ())

    def test_rank_projection_has_stable_ties_and_no_internal_ids(self):
        rows = ranked_people([dict(name='B', points=3, _key='b'), dict(name='A', points=3, _key='a'), dict(name='C', points=0, _key='c')])
        self.assertEqual([row['rank'] for row in rows], [1, 1, 3])
        self.assertFalse(any('_key' in row for row in rows))

    def test_permissions_checked_before_storage_or_writes(self):
        user = NS(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False, has_perm=lambda p: p in ('dic.can_view_dic_operations', 'dic.can_view_dic_scores'))
        request = APIRequestFactory().post('/?edition=1', {}, format='json')
        force_authenticate(request, user=user)
        with patch('dic.activity_scoring_api.record_activity') as service:
            self.assertEqual(ActivityScoringView.as_view()(request).status_code, 403)
            service.assert_not_called()

    def test_unauthorised_booking_cannot_request_scores(self):
        with patch('dic.activity_scoring_api.authorized_grant', return_value=NS()), patch('dic.activity_scoring_api.scoped_orders', return_value=[]), patch('dic.activity_scoring_api.RegistrationOrderItem.objects') as manager, patch('dic.activity_scoring_api.camper_scores') as project:
            manager.filter.return_value.select_related.return_value.first.return_value = None
            # Bypass only atomic wrapper: no database is touched by this unit test.
            with self.assertRaises(NotFound):
                CamperScoringView.get.__wrapped__(CamperScoringView(), NS(query_params={'item': '99'}))
            project.assert_not_called()

    def test_existing_uuid_returns_linked_award_without_new_writes(self):
        actor, edition = NS(pk=1), NS(pk=5)
        data = dict(request_id=uuid4(), activity='SAL01')
        award = NS(submission_fingerprint=fingerprint(data, actor))
        with patch('dic.activity_scoring.require_scoring_staff'), patch('dic.activity_scoring.require_activity_storage'), patch('dic.activity_scoring.CampEdition.objects') as editions, patch('dic.activity_scoring.HouseScoreTransaction.objects') as ledger, patch('dic.activity_scoring.ActivityAward.objects') as awards:
            editions.select_for_update.return_value.get.return_value = edition
            ledger.filter.return_value.first.return_value = NS()
            awards.filter.return_value.first.return_value = award
            self.assertEqual(record_activity.__wrapped__(edition, actor, data), (award, False))
            awards.create.assert_not_called()
            ledger.create.assert_not_called()
            award.submission_fingerprint = 'different'
            with self.assertRaises(ValidationError):
                record_activity.__wrapped__(edition, actor, data)

    def test_reversal_preserves_prerequisite_integrity(self):
        with patch('dic.activity_scoring.activity_storage_ready', return_value=True), patch('dic.activity_scoring.ActivityAward.objects') as manager:
            manager.filter.return_value.first.return_value = NS(pk=1)
            manager.filter.return_value.exclude.return_value = [NS(evidence={'sources': [7]})]
            with self.assertRaises(ValidationError):
                check_reversal_dependencies(NS(pk=7, edition=1))

    def test_individual_posts_one_ledger_contribution_to_current_house(self):
        actor, day = NS(pk=1), date(2026, 12, 20)
        edition = NS(pk=5, year=2026, camp_start_date=day, camp_end_date=day)
        pid = uuid4()
        member = NS(participant_id=pid, house_id=2, participant=NS(full_name='Camper'))
        data = dict(request_id=uuid4(), activity='SAL01', date=day, slot='fajr', participant=pid, verified=True)
        with patch('dic.activity_scoring.require_scoring_staff'), patch('dic.activity_scoring.require_activity_storage'), patch('dic.activity_scoring.CampEdition.objects') as editions, patch('dic.activity_scoring.HouseScoreTransaction.objects') as ledger, patch('dic.activity_scoring.ActivityAward.objects') as awards, patch('dic.activity_scoring.eligible_members', return_value=[member]), patch('dic.activity_scoring.timezone.localdate', return_value=day), patch('dic.activity_scoring.append_score', return_value=(NS(pk=7), True)) as append:
            editions.select_for_update.return_value.get.return_value = edition
            ledger.filter.return_value.first.return_value = None
            awards.filter.return_value.filter.return_value.exists.return_value = False
            record_activity.__wrapped__(edition, actor, data)
            append.assert_called_once()
            self.assertEqual(append.call_args.args[3]['points'], 3)
            self.assertEqual(append.call_args.args[3]['house_id'], 2)
            awards.create.assert_called_once()
            self.assertEqual(awards.create.call_args.kwargs['participant_id'], pid)
            self.assertEqual(awards.create.call_args.kwargs['ledger_entry'].pk, 7)
