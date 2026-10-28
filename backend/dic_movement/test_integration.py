"""Disposable PostgreSQL only. Settlement eligibility is mocked, not certified here."""
import re
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from dic.models import (CampEdition, Participant, PrimaryRegistrant, RegistrationOrder,
    RegistrationOrderItem, RegistrationCategory, CampEnrollment, DigitalIDIssue, CampCheckIn, DICAdminAuditEvent)
from dic.identity_tokens import new_token, read_token
from .models import Movement
from .services import resolve_token, scan_arrival, record_movement, snapshot


class MovementIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_movement_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Only a separately provisioned disposable movement PostgreSQL database is allowed.')
        super().setUpClass()

    def setUp(self):
        self.staff = get_user_model().objects.create_user(username='synthetic-movement-officer', is_staff=True, is_superuser=True)
        self.edition = CampEdition.objects.create(name='SYNTHETIC Movement', year=2098, camp_start_date=date(2098, 12, 1), camp_end_date=date(2098, 12, 10))
        self.other = CampEdition.objects.create(name='SYNTHETIC Other', year=2099, camp_start_date=date(2099, 12, 1), camp_end_date=date(2099, 12, 10))
        self.person = Participant.objects.create(full_name='Synthetic camper', address='Test', phone='', email='',
            date_of_birth=date(2080, 1, 1), sex='Female', height_cm=150, weight_kg=50,
            academic_status='Not Currently in School', occupation='None', marital_status='None')
        registrant = PrimaryRegistrant.objects.create(full_name='Synthetic contact')
        category = RegistrationCategory.objects.create(edition=self.edition, name='Synthetic category')
        order = RegistrationOrder.objects.create(edition=self.edition, primary_registrant=registrant,
            idempotency_key_digest='synthetic-movement', request_fingerprint='synthetic', access_token_digest='synthetic')
        item = RegistrationOrderItem.objects.create(order=order, participant=self.person, category=category,
            category_name_snapshot=category.name, fee_snapshot_ngn=100, participant_snapshot={})
        self.enrollment = CampEnrollment.objects.create(participant=self.person, edition=self.edition,
            source_item=item, participant_number='SYNTHETIC-MOVEMENT-1')
        digest, secret = new_token()
        with patch('dic.participant_services.eligibility', return_value={'eligible': True}):
            self.issue = DigitalIDIssue(enrollment=self.enrollment, version=1, issued_by=self.staff,
                expires_at=timezone.now() + timedelta(days=1), verification_digest=digest, verification_secret=secret)
            self.issue.save(issuance_actor=self.staff)
        self.token = read_token(self.issue)

    def payload(self, action, version, **extra):
        return dict(action=action, confirmed=True, expected_version=version, request_id=str(uuid4()),
            authorization_checked=True, authorization_reference='Synthetic external release evidence' if action == 'departure' else '', **extra)

    def arrive(self):
        with patch('dic_movement.services.eligibility', return_value={'eligible': True}), patch('dic.checkin_services.eligibility', return_value={'eligible': True}):
            return scan_arrival(self.edition, self.token, self.staff)

    def test_initial_scan_arrival_is_idempotent_and_audited(self):
        first, created = self.arrive(); self.assertTrue(created)
        again, created = self.arrive(); self.assertFalse(created)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(first.checked_in_at, again.checked_in_at)
        self.assertEqual(CampCheckIn.objects.count(), 1)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='participant_checked_in').count(), 1)

    def test_departure_return_replay_state_and_audits(self):
        self.arrive()
        departure = self.payload('departure', 0)
        first, created = record_movement(self.edition, self.person.pk, self.staff, departure)
        self.assertTrue(created)
        self.assertEqual(snapshot(self.edition, self.person.pk, self.staff)['presence'], 'outside')
        replay, created = record_movement(self.edition, self.person.pk, self.staff, departure)
        self.assertFalse(created); self.assertEqual(replay.pk, first.pk)
        with self.assertRaises(ValidationError): record_movement(self.edition, self.person.pk, self.staff, self.payload('departure', 1))
        record_movement(self.edition, self.person.pk, self.staff, self.payload('return', 1))
        current = snapshot(self.edition, self.person.pk, self.staff)
        self.assertEqual(current['presence'], 'inside'); self.assertEqual(current['version'], 2)
        self.assertEqual(Movement.objects.count(), 2)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action__in=['camper_departure', 'camper_return']).count(), 2)
        self.assertEqual(Movement.objects.first().recorded_by, self.staff)

    def test_invalid_transition_and_stale_version_do_not_write(self):
        with self.assertRaises(ValidationError): record_movement(self.edition, self.person.pk, self.staff, self.payload('return', 0))
        self.arrive()
        with self.assertRaises(ValidationError): record_movement(self.edition, self.person.pk, self.staff, self.payload('return', 0))
        record_movement(self.edition, self.person.pk, self.staff, self.payload('departure', 0))
        with self.assertRaises(ValidationError): record_movement(self.edition, self.person.pk, self.staff, self.payload('return', 0))
        self.assertEqual(Movement.objects.count(), 1)

    def test_edition_isolation_and_unprivileged_staff(self):
        with patch('dic_movement.services.eligibility', return_value={'eligible': True}):
            self.assertEqual(resolve_token(self.token, self.edition, self.staff).pk, self.enrollment.pk)
            with self.assertRaises(ValidationError): resolve_token(self.token, self.other, self.staff)
        with self.assertRaises(ValidationError): record_movement(self.other, self.person.pk, self.staff, self.payload('departure', 0))
        denied = get_user_model().objects.create_user(username='synthetic-denied', is_staff=True)
        with self.assertRaises(PermissionDenied): record_movement(self.edition, self.person.pk, denied, self.payload('departure', 0))
        self.assertEqual(Movement.objects.count(), 0)

    def test_revoked_token_is_unavailable(self):
        self.issue.revoked_at = timezone.now(); self.issue.revoked_by = self.staff
        self.issue.save(update_fields=['revoked_at', 'revoked_by'], issuance_actor=self.staff)
        with self.assertRaises(ValidationError): resolve_token(self.token, self.edition, self.staff)
