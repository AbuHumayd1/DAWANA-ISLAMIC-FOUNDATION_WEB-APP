"""Prepared, NOT executed: requires separately approved isolated PostgreSQL setup.

Do not run against an existing application database. A normal Django test runner
can apply pending migrations, including dic.0027, unless its migration setup is
explicitly constrained. This module does not create or migrate any DB on import.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError
from dic.test_participant_portal import PortalFixtures
from dic.models import CampCheckIn, CampEdition, House, HouseAllocation, HouseScoreTransaction, DICAdminAuditEvent
from dic.activity_scoring import record_activity
from dic.activity_scoring_api import camper_scores
from dic.scoring_services import reverse_score
from .models import ActivityAward


class AwardFixtures(PortalFixtures):
    def setUp(self):
        PortalFixtures.setUp(self)
        self.day = date(2026, 10, 25)
        self.edition.year = 2026
        self.edition.camp_start_date = self.day - timedelta(days=6)
        self.edition.camp_end_date = self.day + timedelta(days=1)
        self.edition.housing_age_reference_date = date(2026, 12, 23)
        self.edition.save()
        self.clock = patch('dic.activity_scoring.timezone.localdate', return_value=self.day)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.actor = get_user_model().objects.create_user(username='synthetic-activity-officer', is_staff=True, is_superuser=True)
        self.house = House.objects.create(edition=self.edition, name='Synthetic house one', gender='male', capacity=30)
        self.other_house = House.objects.create(edition=self.edition, name='Synthetic house two', gender='male', capacity=30)
        self.allocation = HouseAllocation.objects.create(edition=self.edition, participant=self.item.participant,
            house=self.house, source='admin', status='allocated')
        CampCheckIn.objects.create(edition=self.edition, participant=self.item.participant,
            checked_in_by=self.actor, checked_in_at=datetime.combine(self.edition.camp_start_date, datetime.min.time(), tzinfo=dt_timezone.utc))

    def award(self, code='SAL01', **extra):
        data = dict(activity=code, date=self.day, participant=self.item.participant_id,
            slot='fajr' if code.startswith('SAL0') and code in ('SAL01', 'SAL02', 'SAL03') else '',
            note='Synthetic verified achievement', verified=True, request_id=uuid4())
        data.update(extra)
        return record_activity(self.edition, self.actor, data)


class ActivityAwardIntegrationTests(AwardFixtures, TestCase):
    def test_one_contribution_idempotency_prayer_exclusion_and_reversal(self):
        request_id = uuid4()
        award, created = self.award(request_id=request_id)
        repeated, created_again = self.award(request_id=request_id)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(repeated.pk, award.pk)
        with self.assertRaises(ValidationError):
            self.award('SAL02')
        self.award('SAL03')
        self.assertEqual(ActivityAward.objects.count(), 2)
        self.assertEqual(HouseScoreTransaction.objects.count(), 2)
        self.assertEqual(camper_scores(self.item, 1)['total'], 5)
        reverse_score(self.edition, self.actor, award.ledger_entry_id, dict(reason='Synthetic correction', request_id=uuid4()))
        self.assertEqual(camper_scores(self.item, 1)['total'], 2)
        self.assertEqual(ActivityAward.objects.count(), 2)
        self.assertEqual(HouseScoreTransaction.objects.count(), 3)

    def test_transfer_preserves_original_credit_and_current_house_scope(self):
        first, _ = self.award()
        self.allocation.status = 'reassigned'
        self.allocation.save(update_fields=['status'])
        HouseAllocation.objects.create(edition=self.edition, participant=self.item.participant,
            house=self.other_house, source='admin', status='allocated')
        second, _ = self.award('SAL03')
        first.refresh_from_db()
        self.assertEqual(first.house_id, self.house.pk)
        self.assertEqual(second.house_id, self.other_house.pk)
        scores = camper_scores(self.item, 1)
        self.assertEqual(scores['total'], 5)
        self.assertEqual(scores['house'], self.other_house.name)
        self.assertEqual(scores['house_leaderboard'][0]['points'], 2)

    def test_failed_award_rolls_back_ledger_and_audit(self):
        before = DICAdminAuditEvent.objects.count()
        with patch('dic.activity_scoring.ActivityAward.objects.create', side_effect=RuntimeError('Synthetic failure after ledger insertion')):
            with self.assertRaises(RuntimeError):
                self.award()
        self.assertEqual(HouseScoreTransaction.objects.count(), 0)
        self.assertEqual(ActivityAward.objects.count(), 0)
        self.assertEqual(DICAdminAuditEvent.objects.count(), before)

    def test_daily_caps_and_same_task_cannot_be_relabelled(self):
        self.award('SRV01', slot='task-one')
        with self.assertRaises(ValidationError):
            self.award('SRV06', slot='task-one')
        self.award('SRV02', slot='task-two')
        with self.assertRaises(ValidationError):
            self.award('SRV05', slot='task-three')
        self.award('CHR02', slot='incident-one')
        self.assertEqual(camper_scores(self.item, 1)['total'], 15)

    def test_missing_arrival_rejects_without_posting(self):
        # Synthetic test row only, rolled back by the isolated test transaction.
        CampCheckIn.objects.filter(participant=self.item.participant).delete()
        with self.assertRaises(ValidationError):
            self.award()
        self.assertFalse(HouseScoreTransaction.objects.exists())

    def test_collective_bonus_is_not_personal_and_cannot_repeat(self):
        data = dict(activity='HSP02', date=self.day, house=self.house.pk, verified=True,
            attendees=[self.item.participant_id], exemptions=[], note='Synthetic verified attendance', request_id=uuid4())
        award, created = record_activity(self.edition, self.actor, data)
        self.assertTrue(created)
        self.assertIsNone(award.participant_id)
        self.assertEqual(award.ledger_entry.points, 10)
        self.assertEqual(camper_scores(self.item, 1)['total'], 0)
        with self.assertRaises(ValidationError):
            record_activity(self.edition, self.actor, {**data, 'request_id': uuid4()})

    def test_milestone_requires_underlying_awards_and_protects_reversal(self):
        with self.assertRaises(ValidationError):
            self.award('MIL01')
        sources = [self.award('SAL06', date=self.day - timedelta(days=i))[0] for i in range(3)]
        milestone, _ = self.award('MIL01')
        with self.assertRaises(ValidationError):
            self.award('MIL01')
        with self.assertRaises(ValidationError):
            reverse_score(self.edition, self.actor, sources[0].ledger_entry_id, dict(reason='Synthetic correction', request_id=uuid4()))
        reverse_score(self.edition, self.actor, milestone.ledger_entry_id, dict(reason='Synthetic bonus correction', request_id=uuid4()))
        reverse_score(self.edition, self.actor, sources[0].ledger_entry_id, dict(reason='Synthetic source correction', request_id=uuid4()))


class ActivityAwardConcurrencyTests(AwardFixtures, TransactionTestCase):
    def test_competing_requests_cannot_exceed_service_cap(self):
        self.award('SRV01', slot='first-task')
        edition_id, actor_id, pid, day = self.edition.pk, self.actor.pk, self.item.participant_id, self.day
        def submit(task):
            close_old_connections()
            try:
                record_activity(CampEdition.objects.get(pk=edition_id), get_user_model().objects.get(pk=actor_id),
                    dict(activity='SRV02', date=day, participant=pid, slot=task, verified=True,
                        note='Synthetic concurrent task', request_id=uuid4()))
                return 'recorded'
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, ['second-task', 'third-task']))
        self.assertCountEqual(outcomes, ['recorded', 'rejected'])
        self.assertEqual(sum(ActivityAward.objects.values_list('ledger_entry__points', flat=True)), 10)
