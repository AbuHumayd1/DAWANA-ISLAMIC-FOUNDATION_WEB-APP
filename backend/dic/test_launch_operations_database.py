"""UNEXECUTED database acceptance tests.

Do not run against normal application settings or an existing database. The
owner must first authorize and prove a separate disposable test target. This
module is deliberately excluded from the database-free policy runner.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import threading
from types import SimpleNamespace
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from unittest.mock import patch
from .models import (AcademicClass, AcademicAssignment, CampAnnouncement, CampEdition,
    DICAdminAuditEvent, Participant, PrimaryRegistrant, RegistrationCategory, RegistrationOrder, RegistrationOrderItem)
from .launch_management import save_academic, save_announcement_draft, publish_announcement, StaleLaunchRecord
from .launch_services import assigned_class
from .launch_api import CampUpdatesView


class LaunchFixture:
    def make_edition(self, year):
        return CampEdition.objects.create(name=f'Synthetic Operations {year}', year=year,
            camp_start_date=date(year, 8, 1), camp_end_date=date(year, 8, 7),
            registration_open_date=date(year, 5, 1), registration_close_date=date(year, 7, 1))

    def setUp(self):
        super().setUp()
        self.actor = get_user_model().objects.create_user(username='synthetic-operations', is_staff=True, is_active=True)
        self.actor.user_permissions.set(Permission.objects.filter(content_type__app_label='dic', codename__in=(
            'can_view_dic_operations', 'manage_dic_classes', 'manage_dic_announcements', 'publish_dic_announcements')))
        self.edition, self.other = self.make_edition(2098), self.make_edition(2099)
        self.first = save_academic(AcademicClass(edition=self.edition, name='Class One'), self.actor)
        self.second = save_academic(AcademicClass(edition=self.edition, name='Class Two'), self.actor)

    def registered_camper(self, basis='paid'):
        camper = Participant.objects.create(full_name='Synthetic Camper', address='Synthetic test location',
            phone='00000000000', email='camper@example.test', date_of_birth=date(2000, 1, 1), sex='Male',
            academic_status='Tertiary Student', occupation='None', marital_status='Single')
        registrant = PrimaryRegistrant.objects.create(full_name='Synthetic Guardian', email='guardian@example.test')
        category = RegistrationCategory.objects.create(edition=self.edition, name=f'Category {uuid4()}', fee_ngn=0)
        order = RegistrationOrder.objects.create(edition=self.edition, primary_registrant=registrant,
            registration_basis=basis, payment_status='not_required' if basis == 'tutor' else 'pending',
            idempotency_key_digest=uuid4().hex, request_fingerprint=uuid4().hex,
            access_token_digest=uuid4().hex)
        item = RegistrationOrderItem.objects.create(order=order, participant=camper, category=category,
            category_name_snapshot=category.name, fee_snapshot_ngn=0, participant_snapshot={})
        return camper, item


class LaunchOperationsDatabaseTests(LaunchFixture, TestCase):
    def test_transfer_keeps_assignment_and_immutable_history_and_updates_camper_projection(self):
        camper, item = self.registered_camper()
        row = save_academic(AcademicAssignment(edition=self.edition, participant=camper, academic_class=self.first),
            self.actor, reason='Initial assignment')
        original_pk, version = row.pk, row.updated_at.isoformat()
        row.academic_class = self.second
        save_academic(row, self.actor, expected=version, reason='Reviewed transfer')
        self.assertEqual(AcademicAssignment.objects.filter(edition=self.edition, participant=camper).count(), 1)
        self.assertEqual(row.pk, original_pk)
        audit = DICAdminAuditEvent.objects.filter(target_type='AcademicAssignment', target_id=str(row.pk)).first()
        self.assertEqual(audit.details['before']['academic_class'], self.first.pk)
        self.assertEqual(audit.details['after']['academic_class'], self.second.pk)
        self.assertEqual(assigned_class(camper.pk, self.edition)['name'], self.second.name)
        audit.details = {}
        with self.assertRaises(ValidationError):
            audit.save()

    def test_duplicate_tutor_and_cross_edition_assignments_fail(self):
        camper, item = self.registered_camper()
        save_academic(AcademicAssignment(edition=self.edition, participant=camper, academic_class=self.first), self.actor)
        with self.assertRaises(StaleLaunchRecord):
            save_academic(AcademicAssignment(edition=self.edition, participant=camper, academic_class=self.second), self.actor)
        foreign = save_academic(AcademicClass(edition=self.other, name='Other edition'), self.actor)
        with self.assertRaises(ValidationError):
            save_academic(AcademicAssignment(edition=self.edition, participant=camper, academic_class=foreign), self.actor)
        tutor, item = self.registered_camper('tutor')
        with self.assertRaises(ValidationError):
            save_academic(AcademicAssignment(edition=self.edition, participant=tutor, academic_class=self.first), self.actor)
        self.assertEqual(AcademicAssignment.objects.count(), 1)

    def test_deactivation_preserves_assignment_but_hides_camper_class(self):
        camper, item = self.registered_camper()
        save_academic(AcademicAssignment(edition=self.edition, participant=camper, academic_class=self.first), self.actor)
        version = self.first.updated_at.isoformat()
        self.first.active = False
        save_academic(self.first, self.actor, expected=version)
        self.assertEqual(AcademicAssignment.objects.filter(participant=camper).count(), 1)
        self.assertEqual(assigned_class(camper.pk, self.edition)['status'], 'unassigned')

    def test_published_visibility_and_withdrawal_use_existing_camper_projection(self):
        camper, item = self.registered_camper()
        draft = save_announcement_draft(CampAnnouncement(edition=self.edition, title='Approved notice', body='Safe content'), self.actor)
        future = save_announcement_draft(CampAnnouncement(edition=self.edition, title='Future', body='Not yet visible', starts_at=timezone.now() + timedelta(days=1)), self.actor)
        other = save_announcement_draft(CampAnnouncement(edition=self.other, title='Other edition', body='Not this camp'), self.actor)
        for row in (future, other):
            publish_announcement(row.edition_id, row.pk, self.actor, 'publish', expected=row.updated_at.isoformat())
        def updates():
            with patch('dic.launch_api.portal_item', return_value=item):
                return CampUpdatesView().get(SimpleNamespace(query_params={'item_id': str(item.pk), 'edition': str(self.other.pk)})).data['announcements']
        self.assertEqual(updates(), [])
        row = publish_announcement(self.edition.pk, draft.pk, self.actor, 'publish', expected=draft.updated_at.isoformat())
        self.assertEqual([entry['id'] for entry in updates()], [row.pk])
        stale = CampAnnouncement.objects.get(pk=row.pk)
        row = publish_announcement(self.edition.pk, row.pk, self.actor, 'withdraw', expected=row.updated_at.isoformat())
        self.assertEqual(updates(), [])
        with self.assertRaises(StaleLaunchRecord):
            save_announcement_draft(stale, self.actor, expected=stale.updated_at.isoformat())
        self.assertEqual(CampAnnouncement.objects.get(pk=row.pk).status, 'draft')


class LaunchOperationsConcurrencyTests(LaunchFixture, TransactionTestCase):
    def test_two_stale_editors_cannot_overwrite_each_other(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Real row-lock acceptance requires an explicitly authorized disposable PostgreSQL target.')
        barrier = threading.Barrier(2)
        version = self.first.updated_at.isoformat()
        def edit(name):
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                row = AcademicClass.objects.get(pk=self.first.pk)
                row.name = name
                barrier.wait(timeout=15)
                try:
                    save_academic(row, actor, expected=version)
                    return 'saved'
                except StaleLaunchRecord:
                    return 'conflict'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(edit, name) for name in ('Concurrent One', 'Concurrent Two')]
            results = [future.result(timeout=30) for future in futures]
        self.assertCountEqual(results, ['saved', 'conflict'])
