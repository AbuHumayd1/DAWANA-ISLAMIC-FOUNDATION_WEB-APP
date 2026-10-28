"""Database-free scoring tests. Transaction/constraint integration needs approval."""
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import HouseScoreTransaction
from .scoring_api import HouseScoringView, HouseScoreReversalView, ScoreEntryInput, ScoreReversalInput
from .scoring_services import combined_leaderboard, record_score, reverse_score, scoring_houses


class HouseScoringTests(SimpleTestCase):
    def user(self, *, staff=True, active=True, operations=True, view=True, record=True, correct=True, export=True):
        allowed = {name for name, enabled in [
            ('can_view_dic_operations', operations), ('can_view_dic_scores', view),
            ('can_record_dic_scores', record), ('can_correct_dic_scores', correct),
            ('can_export_dic_reports', export)] if enabled}
        return NS(pk=7, is_authenticated=True, is_active=active, is_staff=staff, is_superuser=False,
            has_perm=lambda permission: permission in {f'dic.{name}' for name in allowed},
            get_full_name=lambda: 'Scoring Staff', get_username=lambda: 'scorer')

    def request(self, user, method='get', query='', body=None, reverse=False):
        request = getattr(APIRequestFactory(), method)('/api/v1/dic/operations/scoring/'+query, body or {}, format='json')
        if user is not None:
            force_authenticate(request, user=user)
        return HouseScoreReversalView.as_view()(request, entry_id=1) if reverse else HouseScoringView.as_view()(request)

    def house(self, pk, name, gender='Male', colour=''):
        return NS(pk=pk, name=name, gender=gender, badge_colour=colour)

    def test_combined_math_ties_zero_negative_and_stable_secondary_order(self):
        houses = [self.house(1, 'Zulu'), self.house(2, 'Alpha', 'Female', '#123456'), self.house(3, 'Zero'), self.house(4, 'Negative')]
        entries = [NS(house_id=1, entry_type='award', points=8), NS(house_id=2, entry_type='award', points=12),
            NS(house_id=2, entry_type='deduction', points=4), NS(house_id=4, entry_type='deduction', points=3)]
        rows = combined_leaderboard(houses, entries)
        self.assertEqual([row['name'] for row in rows], ['Alpha', 'Zulu', 'Zero', 'Negative'])
        self.assertEqual([row['rank'] for row in rows], [1, 1, 3, 4])
        self.assertEqual([row['net'] for row in rows], [8, 8, 0, -3])
        self.assertEqual((rows[0]['awarded'], rows[0]['deducted'], rows[0]['colour']), (12, 4, '#123456'))
        self.assertIsNone(rows[1]['colour'])

    def test_all_eight_configured_houses_include_both_genders_and_zero_scores(self):
        houses = [self.house(pk, f'House {pk}', 'Male' if pk <= 4 else 'Female') for pk in range(1, 9)]
        rows = combined_leaderboard(houses, [])
        self.assertEqual(len(rows), 8)
        self.assertEqual({row['gender'] for row in rows}, {'Male', 'Female'})
        self.assertTrue(all(row['rank'] == 1 and row['net'] == 0 for row in rows))
        self.assertEqual(combined_leaderboard([], []), [])
        self.assertEqual(len(combined_leaderboard(houses[:3], [])), 3)

    def test_house_query_scopes_edition_without_gender_or_status_filter(self):
        edition = NS(pk=41)
        with patch('dic.scoring_services.House.objects') as manager:
            scoring_houses(edition)
        manager.filter.assert_called_once_with(edition=edition, purpose='participants')

    def test_denied_users_cannot_read_record_or_correct(self):
        for user in (None, AnonymousUser(), self.user(staff=False), self.user(active=False), self.user(operations=False), self.user(view=False)):
            for method, reverse in [('get', False), ('post', False), ('post', True)]:
                with self.subTest(user=user, method=method, reverse=reverse), patch('dic.scoring_api.require_scoring_storage') as storage:
                    self.assertEqual(self.request(user, method, reverse=reverse).status_code, 403)
                    storage.assert_not_called()
        for user, reverse in [(self.user(record=False), False), (self.user(correct=False), True)]:
            with patch('dic.scoring_api.require_scoring_storage') as storage:
                self.assertEqual(self.request(user, 'post', reverse=reverse).status_code, 403)
                storage.assert_not_called()

    def test_session_csrf_is_enforced_for_both_write_routes(self):
        for view, kwargs in [(HouseScoringView, {}), (HouseScoreReversalView, {'entry_id': 1})]:
            request = APIRequestFactory(enforce_csrf_checks=True).post('/api/v1/dic/operations/scoring/?edition=41', {}, format='json')
            request.user = self.user()
            with patch('dic.scoring_api.require_scoring_storage') as storage:
                response = view.as_view()(request, **kwargs)
            self.assertEqual(response.status_code, 403)
            self.assertIn('CSRF', str(response.data))
            storage.assert_not_called()

    def test_server_input_rejects_invalid_points_types_reasons_and_references(self):
        valid = dict(house=1, entry_type='award', points=12, activity='Agreed activity', request_id=str(uuid4()))
        self.assertTrue(ScoreEntryInput(data=valid).is_valid())
        for changes in [dict(points=0), dict(points=-1), dict(points=1.5), dict(points=2147483648),
                dict(activity=' '), dict(entry_type='invented'), dict(house=0), dict(request_id='invalid'), dict(note='a'*1001)]:
            with self.subTest(changes=changes):
                self.assertFalse(ScoreEntryInput(data={**valid, **changes}).is_valid())
        self.assertFalse(ScoreReversalInput(data=dict(reason=' ', request_id=str(uuid4()))).is_valid())

    def service_context(self, existing=None, original=None, already_reversed=False, house=True):
        stack = ExitStack()
        edition = stack.enter_context(patch('dic.scoring_services.CampEdition.objects'))
        houses = stack.enter_context(patch('dic.scoring_services.House.objects'))
        ledger = stack.enter_context(patch('dic.scoring_services.HouseScoreTransaction.objects'))
        audit = stack.enter_context(patch('dic.scoring_services.DICAdminAuditEvent.objects'))
        houses.filter.return_value.order_by.return_value.filter.return_value.first.return_value = NS(pk=2) if house else None
        def lookup(**kwargs):
            value = original if 'pk' in kwargs else existing
            return NS(first=lambda: value, exists=lambda: already_reversed)
        ledger.filter.side_effect = lookup
        ledger.create.side_effect = lambda **kwargs: NS(pk=99, **kwargs)
        return stack, edition, houses, ledger, audit

    def payload(self):
        return dict(house=2, entry_type='award', points=12, activity='Agreed activity', note='', request_id=uuid4())

    def test_record_uses_selected_house_staff_server_time_and_one_audit(self):
        stack, editions, houses, ledger, audit = self.service_context()
        edition, actor, data = NS(pk=41), self.user(), self.payload()
        with stack:
            row, created = record_score.__wrapped__(edition, actor, data)
        self.assertTrue(created)
        self.assertEqual((row.edition.pk, row.house_id, row.points), (41, 2, 12))
        self.assertIs(row.created_by, actor)
        editions.select_for_update.return_value.get.assert_called_once_with(pk=41)
        houses.filter.assert_called_once_with(edition=edition, purpose='participants')
        ledger.create.assert_called_once()
        audit.create.assert_called_once()
        self.assertEqual(audit.create.call_args.kwargs['action'], 'house_score_recorded')
        self.assertIs(HouseScoreTransaction._meta.get_field('created_at').default, timezone.now)

    def test_duplicate_retries_do_not_create_or_audit_and_changed_payload_is_rejected(self):
        data = self.payload()
        original = NS(pk=9, house_id=2, entry_type='award', points=12, activity='Agreed activity', note='', reverses_id=None)
        stack, _, _, ledger, audit = self.service_context(existing=original)
        with stack:
            row, created = record_score.__wrapped__(NS(pk=41), self.user(), data)
            self.assertIs(row, original)
            self.assertFalse(created)
            with self.assertRaises(ValidationError):
                record_score.__wrapped__(NS(pk=41), self.user(), {**data, 'points': 13})
        ledger.create.assert_not_called()
        audit.create.assert_not_called()

    def test_other_edition_house_is_rejected_without_writes(self):
        stack, _, houses, ledger, audit = self.service_context(house=False)
        with stack, self.assertRaises(ValidationError):
            record_score.__wrapped__(NS(pk=41), self.user(), self.payload())
        houses.filter.assert_called_once_with(edition=NS(pk=41), purpose='participants')
        ledger.create.assert_not_called()
        audit.create.assert_not_called()

    def test_reversal_retains_original_and_adds_equal_opposing_points_and_audit(self):
        for kind, expected in [('award', 'deduction'), ('deduction', 'award')]:
            original = NS(pk=5, house_id=2, entry_type=kind, points=12, activity='Original activity', reverses_id=None)
            stack, _, _, ledger, audit = self.service_context(original=original)
            with stack:
                row, created = reverse_score.__wrapped__(NS(pk=41), self.user(), 5, dict(reason='Wrong entry', request_id=uuid4()))
            self.assertTrue(created)
            self.assertEqual((row.points, row.entry_type, row.reverses_id), (12, expected, 5))
            self.assertEqual(original.entry_type, kind)
            self.assertEqual(row.note, 'Wrong entry')
            ledger.create.assert_called_once()
            self.assertEqual(audit.create.call_args.kwargs['action'], 'house_score_reversed')
            rows = combined_leaderboard([self.house(2, 'One')], [original, row])
            self.assertEqual(rows[0]['net'], 0)

    def test_cross_edition_missing_original_and_second_reversal_are_rejected(self):
        cases = [(None, False), (NS(pk=5, reverses_id=1), False),
            (NS(pk=5, house_id=2, points=5, activity='Activity', entry_type='award', reverses_id=None), True)]
        for original, reversed_already in cases:
            stack, _, _, ledger, audit = self.service_context(original=original, already_reversed=reversed_already)
            with stack, self.assertRaises(ValidationError):
                reverse_score.__wrapped__(NS(pk=41), self.user(), 5, dict(reason='Wrong', request_id=uuid4()))
            self.assertEqual(ledger.filter.call_args_list[0].kwargs, dict(edition=NS(pk=41), pk=5))
            ledger.create.assert_not_called()
            audit.create.assert_not_called()

    def test_reversal_retry_returns_same_record_without_audit(self):
        original = NS(pk=5, house_id=2, points=5, activity='Activity', entry_type='award', reverses_id=None)
        reversed_row = NS(pk=6, house_id=2, points=5, activity='Activity', entry_type='deduction', reverses_id=5, note='Wrong')
        stack, _, _, ledger, audit = self.service_context(existing=reversed_row, original=original, already_reversed=True)
        with stack:
            row, created = reverse_score.__wrapped__(NS(pk=41), self.user(), 5, dict(reason='Wrong', request_id=uuid4()))
        self.assertIs(row, reversed_row)
        self.assertFalse(created)
        ledger.create.assert_not_called()
        audit.create.assert_not_called()

    def test_service_permissions_cannot_be_bypassed_by_calling_commands_directly(self):
        with patch('dic.scoring_services.CampEdition.objects') as editions:
            with self.assertRaises(PermissionDenied):
                record_score.__wrapped__(NS(pk=41), self.user(record=False), self.payload())
            with self.assertRaises(PermissionDenied):
                reverse_score.__wrapped__(NS(pk=41), self.user(correct=False), 5, dict(reason='Wrong', request_id=uuid4()))
        editions.select_for_update.assert_not_called()

    def test_write_routes_require_explicit_edition_and_authorized_post_is_idempotent(self):
        data = self.payload(); data['request_id'] = str(data['request_id'])
        with patch('dic.scoring_api.require_scoring_storage'), \
             patch('dic.scoring_api._edition_from_request', return_value=NS(pk=41)), \
             patch('dic.scoring_api.record_score', side_effect=[(NS(pk=9), True), (NS(pk=9), False)]):
            self.assertEqual(self.request(self.user(), 'post', body=data).status_code, 400)
            first = self.request(self.user(), 'post', '?edition=41', data)
            second = self.request(self.user(), 'post', '?edition=41', data)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertIn('no-store', first['Cache-Control'])

    def read_context(self):
        stack = ExitStack()
        stack.enter_context(patch('dic.scoring_api.require_scoring_storage'))
        select = stack.enter_context(patch('dic.scoring_api._edition_from_request', return_value=NS(pk=41, name='Test Camp')))
        houses = stack.enter_context(patch('dic.scoring_api.scoring_houses', return_value=[self.house(2, '<House>', 'Female')]))
        ledger = stack.enter_context(patch('dic.scoring_api.HouseScoreTransaction.objects'))
        entries = ledger.filter.return_value
        entries.__iter__.return_value = iter([])
        entries.count.return_value = 0
        entries.select_related.return_value.order_by.return_value = []
        editions = stack.enter_context(patch('dic.scoring_api.CampEdition.objects'))
        editions.order_by.return_value.values.return_value = []
        return stack, select, houses, ledger

    def test_read_only_view_scopes_edition_keeps_zero_houses_and_private_fields_absent(self):
        stack, select, houses, ledger = self.read_context()
        with stack:
            response = self.request(self.user(record=False, correct=False), query='?edition=41')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(select.call_args.args[0].query_params['edition'], '41')
        houses.assert_called_once_with(NS(pk=41, name='Test Camp'))
        ledger.filter.assert_called_once_with(edition=NS(pk=41, name='Test Camp'))
        self.assertEqual(response.data['leaderboard'][0]['net'], 0)
        self.assertEqual(response.data['history'], [])
        for field in ('email', 'phone', 'verification_secret', 'participant'):
            self.assertNotIn(field, str(response.data))

    def test_print_requires_both_scoring_and_existing_export_access_and_escapes_html(self):
        with patch('dic.scoring_api.require_scoring_storage') as storage:
            self.assertEqual(self.request(self.user(export=False), query='?print=history').status_code, 403)
            storage.assert_not_called()
        for report in ('leaderboard', 'history'):
            stack, _, _, _ = self.read_context()
            with stack:
                response = self.request(self.user(), query=f'?edition=41&print={report}')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '&lt;House&gt;')
            self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_storage_pending_and_unique_request_and_reversal_constraints(self):
        with patch('dic.scoring_services.connection') as connection:
            connection.introspection.table_names.return_value = []
            response = self.request(self.user())
        self.assertEqual(response.status_code, 503)
        self.assertIn('setup is pending', str(response.data))
        self.assertIn(('edition', 'request_id'), [getattr(item, 'fields', ()) for item in HouseScoreTransaction._meta.constraints])
        self.assertTrue(HouseScoreTransaction._meta.get_field('reverses').unique)
        self.assertEqual(HouseScoreTransaction._meta.default_permissions, ())


class HouseScoringIntegrationTests(TestCase):
    """Real transactions/audits in the runner's isolated database only."""
    def setUp(self):
        from datetime import date
        from django.contrib.auth import get_user_model
        from .models import CampEdition, House
        from .house_configuration import approved_2026_houses
        self.edition = CampEdition.objects.create(name='SYNTHETIC 2026 scoring validation', year=2026,
            camp_start_date=date(2026,12,23), camp_end_date=date(2027,1,1), housing_age_reference_date=date(2026,12,23))
        self.actor = get_user_model().objects.create_user(username='synthetic-scoring-validator', is_staff=True, is_superuser=True)
        self.houses = [House.objects.create(edition=self.edition, name=row['name'], gender=row['gender'],
            capacity=row['capacity'], status=row['status'], purpose=row['purpose'], badge_colour=row['badge_colour']) for row in approved_2026_houses()]

    def test_actual_2026_inventory_approves_eight_30_person_houses_without_reserves(self):
        from .housing_policy import validate_inventory
        houses = validate_inventory(self.edition)
        self.assertEqual(len(houses), 8)
        self.assertEqual(sum(house.capacity for house in houses), 240)
        self.assertEqual(sum(house.gender=='male' for house in houses), 4)
        self.assertEqual(sum(house.gender=='female' for house in houses), 4)
        self.assertTrue(all(house.status=='active' for house in houses))

    def test_persisted_awards_deductions_reversals_deduplication_and_audits(self):
        from .models import DICAdminAuditEvent
        data = dict(house=self.houses[0].pk, entry_type='award', points=12, activity='SYNTHETIC approved activity', note='', request_id=uuid4())
        award, created = record_score(self.edition, self.actor, data)
        self.assertTrue(created)
        repeated, created = record_score(self.edition, self.actor, data)
        self.assertFalse(created)
        self.assertEqual((repeated.pk, repeated.created_at), (award.pk, award.created_at))
        record_score(self.edition, self.actor, {**data, 'entry_type':'deduction', 'points':4, 'request_id':uuid4()})
        rows = combined_leaderboard(self.houses, HouseScoreTransaction.objects.filter(edition=self.edition))
        self.assertEqual(next(row for row in rows if row['house_id']==award.house_id)['net'], 8)
        correction = dict(reason='SYNTHETIC entry correction', request_id=uuid4())
        reversal, created = reverse_score(self.edition, self.actor, award.pk, correction)
        self.assertTrue(created)
        same, created = reverse_score(self.edition, self.actor, award.pk, correction)
        self.assertFalse(created)
        self.assertEqual(same.pk, reversal.pk)
        self.assertEqual(reversal.reverses_id, award.pk)
        with self.assertRaises(ValidationError):
            reverse_score(self.edition, self.actor, award.pk, {**correction, 'request_id':uuid4()})
        self.assertEqual(HouseScoreTransaction.objects.filter(edition=self.edition).count(), 3)
        self.assertEqual(DICAdminAuditEvent.objects.filter(target_type='HouseScoreTransaction', actor=self.actor).count(), 3)
        rows = combined_leaderboard(self.houses, HouseScoreTransaction.objects.filter(edition=self.edition))
        self.assertEqual(len(rows), 8)
        self.assertEqual(next(row for row in rows if row['house_id']==award.house_id)['net'], -4)
        self.assertEqual(HouseScoreTransaction.objects.get(pk=award.pk).points, 12)

    def test_real_database_rejects_cross_edition_house_and_reversal(self):
        from datetime import date
        from .models import CampEdition, House
        other = CampEdition.objects.create(name='SYNTHETIC other edition', year=2027,
            camp_start_date=date(2027,12,23), camp_end_date=date(2028,1,1))
        foreign_house = House.objects.create(edition=other, name='SYNTHETIC other house', gender='male', capacity=25)
        data = dict(house=foreign_house.pk, entry_type='award', points=5, activity='SYNTHETIC activity', note='', request_id=uuid4())
        with self.assertRaises(ValidationError):
            record_score(self.edition, self.actor, data)
        original, _ = record_score(other, self.actor, data)
        with self.assertRaises(ValidationError):
            reverse_score(self.edition, self.actor, original.pk, dict(reason='SYNTHETIC correction', request_id=uuid4()))
        self.assertEqual(HouseScoreTransaction.objects.filter(edition=self.edition).count(), 0)
