"""Database-free tests: permission/CSRF boundaries, eligibility and idempotency.

ORM calls are isolated; real transaction/unique-constraint checks require a
separately approved isolated database. This suite never creates one.
"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from .checkin_api import CampCheckInView
from .checkin_services import check_in_participant, candidate_for, checkin_directory
from .models import CampCheckIn


class CampCheckInTests(SimpleTestCase):
    def user(self, staff=True, active=True, operations=True, checkin=True, export=True):
        return SimpleNamespace(pk=7, is_authenticated=True, is_active=active,
            is_staff=staff, is_superuser=False,
            get_full_name=lambda: 'Test Staff', get_username=lambda: 'test-staff',
            has_perm=lambda permission: permission in {
                name for name, enabled in [('dic.can_view_dic_operations', operations),
                ('dic.can_check_in_dic_participants', checkin), ('dic.can_export_dic_reports', export)] if enabled})

    def request(self, user, method='get', query='', body=None):
        request = getattr(APIRequestFactory(), method)('/api/v1/dic/operations/check-in/'+query, body or {}, format='json')
        if user is not None:
            force_authenticate(request, user=user)
        return CampCheckInView.as_view()(request)

    def test_denied_users_cannot_read_or_check_in(self):
        for user in (None, AnonymousUser(), self.user(staff=False), self.user(active=False), self.user(operations=False)):
            for method in ('get', 'post'):
                with self.subTest(user=user, method=method), patch('dic.checkin_api.require_checkin_storage') as storage:
                    self.assertEqual(self.request(user, method).status_code, 403)
                    storage.assert_not_called()
        with patch('dic.checkin_api.require_checkin_storage') as storage:
            self.assertEqual(self.request(self.user(checkin=False), 'post').status_code, 403)
            storage.assert_not_called()

    def test_session_post_requires_csrf_before_any_storage_access(self):
        request = APIRequestFactory(enforce_csrf_checks=True).post('/api/v1/dic/operations/check-in/?edition=41', {}, format='json')
        request.user = self.user()
        with patch('dic.checkin_api.require_checkin_storage') as storage:
            response = CampCheckInView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn('CSRF', str(response.data))
        storage.assert_not_called()

    def test_list_scopes_edition_search_pagination_and_retains_no_store(self):
        edition = SimpleNamespace(pk=41, name='Test Camp')
        rows = [dict(name=f'Person {index}') for index in range(30)]
        totals = dict(registered=30, checked_in=8, not_yet_arrived=22, needs_attention=3)
        with patch('dic.checkin_api.require_checkin_storage'), \
             patch('dic.checkin_api._edition_from_request', return_value=edition), \
             patch('dic.checkin_api.checkin_directory', return_value=(rows, totals)) as directory, \
             patch('dic.checkin_api.CampEdition.objects') as editions:
            editions.order_by.return_value.values.return_value = []
            response = self.request(self.user(checkin=False), query='?edition=41&search=Person&page=2')
        self.assertEqual(response.status_code, 200)
        directory.assert_called_once_with(edition, 'Person')
        self.assertEqual(response.data['results'], rows[25:])
        self.assertEqual(response.data['totals'], totals)
        self.assertEqual(response.data['count'], 30)
        self.assertIn('no-store', response['Cache-Control'])

    def test_print_requires_export_permission_and_escapes_names(self):
        with patch('dic.checkin_api.require_checkin_storage') as storage:
            self.assertEqual(self.request(self.user(export=False), query='?print=1').status_code, 403)
            storage.assert_not_called()
        row = dict(name='<script>unsafe</script>', registration_number='SYNTHETIC', participant_number='SYNTHETIC',
            registration_status='confirmed', payment_status='paid', eligibility=dict(label='Verified'), house=None, check_in=None)
        with patch('dic.checkin_api.require_checkin_storage'), \
             patch('dic.checkin_api._edition_from_request', return_value=SimpleNamespace(pk=41, name='Test Camp')), \
             patch('dic.checkin_api.checkin_directory', return_value=([row], {})):
            response = self.request(self.user(), query='?edition=41&print=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '&lt;script&gt;unsafe&lt;/script&gt;')
        self.assertNotContains(response, '<script>unsafe</script>')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_post_requires_explicit_edition_and_valid_participant(self):
        with patch('dic.checkin_api.require_checkin_storage'), \
             patch('dic.checkin_api._edition_from_request'), \
             patch('dic.checkin_api.check_in_participant') as command:
            for query, body in [('', {'participant_id': str(uuid4())}), ('?edition=41', {'participant_id':'bad'})]:
                self.assertEqual(self.request(self.user(), 'post', query, body).status_code, 400)
            command.assert_not_called()

    def command_context(self, eligible=True, existing=None):
        # Bypass only the transaction decorator; no database is permitted here.
        # The real permission function, candidate construction and write branch run.
        stack = __import__('contextlib').ExitStack()
        mocks = {}
        for name in ('RegistrationOrderItem', 'RegistrationOrder', 'Participant', 'CampEnrollment', 'CampCheckIn', 'DICAdminAuditEvent'):
            mocks[name] = stack.enter_context(patch(f'dic.checkin_services.{name}.objects'))
        sources = mocks['RegistrationOrderItem'].filter.return_value
        sources.values_list.return_value = [11]
        sources.select_related.return_value.order_by.return_value.first.return_value = SimpleNamespace(
            pk=22, participant_id=33, order=SimpleNamespace(edition_id=41))
        mocks['CampEnrollment'].select_for_update.return_value.filter.return_value.first.return_value = None
        mocks['CampCheckIn'].filter.return_value.select_related.return_value.first.return_value = existing
        mocks['CampCheckIn'].get_or_create.return_value = (SimpleNamespace(pk=9), True)
        mocks['eligibility'] = stack.enter_context(patch('dic.checkin_services.eligibility',
            return_value=dict(eligible=eligible, code='verified_paid' if eligible else 'registration_not_verified_paid')))
        return stack, mocks

    def test_authorized_post_and_repeat_return_original_staff_and_time(self):
        participant = uuid4()
        row = SimpleNamespace(checked_in_at=timezone.now(), checked_in_by=self.user())
        with patch('dic.checkin_api.require_checkin_storage'), \
             patch('dic.checkin_api._edition_from_request', return_value=SimpleNamespace(pk=41)), \
             patch('dic.checkin_api.check_in_participant', side_effect=[(row, True), (row, False)]):
            first = self.request(self.user(), 'post', '?edition=41', {'participant_id': str(participant)})
            repeated = self.request(self.user(), 'post', '?edition=41', {'participant_id': str(participant)})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(first.data['check_in'], repeated.data['check_in'])
        self.assertEqual(first.data['check_in']['staff'], 'Test Staff')
        self.assertIn('no-store', first['Cache-Control'])

    def test_ineligible_arrival_cannot_write_record_or_audit(self):
        stack, mocks = self.command_context(eligible=False)
        with stack, self.assertRaises(ValidationError):
            check_in_participant.__wrapped__(SimpleNamespace(pk=41), 33, self.user())
        mocks['CampCheckIn'].get_or_create.assert_not_called()
        mocks['DICAdminAuditEvent'].create.assert_not_called()
        self.assertEqual(mocks['eligibility'].call_args.args[0].source_item_id, 22)

    def test_eligible_arrival_records_server_time_actor_and_one_audit(self):
        stack, mocks = self.command_context()
        actor = self.user()
        edition = SimpleNamespace(pk=41)
        with stack:
            row, created = check_in_participant.__wrapped__(edition, 33, actor)
        self.assertTrue(created)
        self.assertEqual(row.pk, 9)
        defaults = mocks['CampCheckIn'].get_or_create.call_args.kwargs['defaults']
        self.assertIs(defaults['checked_in_by'], actor)
        self.assertTrue(timezone.is_aware(defaults['checked_in_at']))
        mocks['DICAdminAuditEvent'].create.assert_called_once()
        mocks['RegistrationOrder'].select_for_update.assert_called_once()
        mocks['Participant'].select_for_update.assert_called_once()
        mocks['RegistrationOrder'].update.assert_not_called()

    def test_duplicate_retains_original_arrival_and_does_not_reaudit(self):
        original = SimpleNamespace(pk=9, checked_in_at=timezone.now(), checked_in_by=self.user())
        stack, mocks = self.command_context(existing=original)
        with stack:
            row, created = check_in_participant.__wrapped__(SimpleNamespace(pk=41), 33, self.user())
        self.assertIs(row, original)
        self.assertFalse(created)
        mocks['CampCheckIn'].get_or_create.assert_not_called()
        mocks['DICAdminAuditEvent'].create.assert_not_called()
        mocks['eligibility'].assert_not_called()

    def test_source_changes_abort_and_model_has_edition_unique_constraint(self):
        stack, mocks = self.command_context()
        mocks['RegistrationOrderItem'].filter.return_value.values_list.side_effect = [[11], [11, 12]]
        with stack, self.assertRaises(ValidationError):
            check_in_participant.__wrapped__(SimpleNamespace(pk=41), 33, self.user())
        mocks['CampCheckIn'].get_or_create.assert_not_called()
        self.assertIn(('participant', 'edition'), [constraint.fields for constraint in CampCheckIn._meta.constraints])
        self.assertFalse(CampCheckIn._meta.get_field('checked_in_by').null)
        self.assertEqual(CampCheckIn._meta.default_permissions, ())

    def test_directory_deduplicates_and_totals_are_not_search_totals(self):
        edition = SimpleNamespace(pk=41)
        def item(number, name):
            return SimpleNamespace(pk=number, participant_id=number, participant=SimpleNamespace(full_name=name),
                    order_id=number+10, order=SimpleNamespace(edition_id=41, public_id=f'REG-{number}', status='confirmed', payment_status='paid', registration_basis='paid'))
        first, second = item(1, 'Aisha'), item(2, 'Musa')
        arrival = SimpleNamespace(participant_id=1, checked_in_at=timezone.now(), checked_in_by=self.user())
        with patch('dic.checkin_services.RegistrationOrderItem.objects') as items, \
             patch('dic.checkin_services.CampEnrollment.objects') as enrollments, \
             patch('dic.checkin_services.CampCheckIn.objects') as arrivals, \
             patch('dic.checkin_services.HouseAllocation.objects') as houses, \
             patch('dic.checkin_services.eligibility', side_effect=[dict(eligible=True,code='verified_paid'), dict(eligible=False,code='registration_not_verified_paid')]):
            items.filter.return_value.select_related.return_value.order_by.return_value = [first, first, second]
            enrollments.filter.return_value = []
            arrivals.filter.return_value.select_related.return_value = [arrival]
            houses.filter.return_value.select_related.return_value = []
            rows, totals = checkin_directory(edition, 'MUSA')
            items.filter.assert_called_once_with(order__edition=edition)
            arrivals.filter.assert_called_once_with(edition=edition)
        self.assertEqual([row['name'] for row in rows], ['Musa'])
        self.assertEqual(totals, dict(registered=2, checked_in=1, not_yet_arrived=1, needs_attention=1))
        self.assertIsNone(rows[0]['house'])
        self.assertIsNone(rows[0]['check_in'])

    def test_missing_storage_returns_service_unavailable_without_data_reads(self):
        with patch('dic.checkin_services.connection') as connection, \
             patch('dic.checkin_api.checkin_directory') as directory:
            connection.introspection.table_names.return_value = []
            response = self.request(self.user())
        self.assertEqual(response.status_code, 503)
        self.assertIn('setup is pending', str(response.data))
        directory.assert_not_called()

    def test_candidate_does_not_create_enrollment_or_issue_credentials(self):
        candidate = candidate_for(SimpleNamespace(pk=1, participant_id=2, order=SimpleNamespace(edition_id=3)))
        self.assertEqual((candidate.source_item_id, candidate.participant_id, candidate.edition_id), (1, 2, 3))
        self.assertEqual(candidate.source_review_fingerprint, '')
