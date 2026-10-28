"""Database-free policy/API tests; never use development records."""
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from .api import ScanView, MovementView
from .services import require, resolve_token, presence, validate_transition, departure_authority, record_movement, scan_arrival


BASE = {'dic.can_view_dic_operations', 'dic.can_view_dic_ids', 'dic.can_check_in_dic_participants'}
MOVEMENT = {'dic_movement.can_view_movements', 'dic_movement.can_record_movements', 'dic_movement.can_authorize_departure'}


class MovementPolicyTests(SimpleTestCase):
    def actor(self, permissions=None, **changes):
        values = dict(pk=7, is_authenticated=True, is_active=True, is_staff=True, is_superuser=False,
            has_perm=lambda permission: permission in (BASE | MOVEMENT if permissions is None else permissions))
        return NS(**{**values, **changes})

    def request(self, view, user, method='post', query='?edition=1', data=None):
        request = getattr(APIRequestFactory(), method)('/api/v1/dic/operations/scan/' + query, data or {}, format='json')
        if user:
            force_authenticate(request, user=user)
        return view.as_view()(request)

    def payload(self, **changes):
        return dict(action='departure', confirmed=True, authorization_checked=True,
            authorization_reference='SYNTHETIC release', expected_version=0, request_id=str(uuid4()), **changes)

    def test_active_staff_and_separate_permission_required(self):
        for changes in [dict(is_active=False), dict(is_staff=False), dict(is_authenticated=False)]:
            with self.assertRaises(PermissionDenied): require(self.actor(**changes), 'dic_movement.can_view_movements')
        with self.assertRaises(PermissionDenied): require(self.actor(BASE), 'dic_movement.can_record_movements')

    def test_anonymous_and_nonoperations_denied_before_storage(self):
        for view in [ScanView, MovementView]:
            for actor in [None, self.actor(set()), self.actor(is_staff=False)]:
                with patch('dic_movement.api.storage') as storage, patch('dic_movement.services.DigitalIDIssue') as ids:
                    self.assertEqual(self.request(view, actor).status_code, 403)
                    storage.assert_not_called(); ids.objects.filter.assert_not_called()

    def test_history_requires_view_permission_even_with_record_authority(self):
        actor = self.actor(BASE | {'dic_movement.can_record_movements'})
        with patch('dic_movement.api.storage') as storage:
            self.assertEqual(self.request(MovementView, actor, method='get').status_code, 403)
            storage.assert_not_called()

    @patch('dic.operations_api._paginate', return_value={'results': []})
    @patch('dic.operations_api.DICAdminAuditEvent')
    def test_general_audit_feed_does_not_bypass_movement_view_permission(self, audit, paginate):
        from dic.operations_api import OperationsActivityView
        actor = self.actor(BASE | {'dic.can_view_dic_audit'})
        query = audit.objects.select_related.return_value.all.return_value
        self.assertEqual(self.request(OperationsActivityView, actor, method='get').status_code, 200)
        query.exclude.assert_called_once_with(action__in=['camper_departure', 'camper_return'])

    def test_explicit_edition_required(self):
        self.assertEqual(self.request(ScanView, self.actor(), query='', data={'token': 'A' * 43}).status_code, 400)

    @patch('dic_movement.services.DigitalIDIssue')
    def test_invalid_tokens_never_query_identity(self, ids):
        for token in [None, '', '123', 'A' * 44, 'https://example.test/#secret']:
            with self.assertRaises(ValidationError): resolve_token(token, NS(pk=1), self.actor())
        ids.objects.filter.assert_not_called()

    @patch('dic_movement.services.DigitalIDIssue')
    def test_id_view_alone_does_not_grant_operational_scanning(self, ids):
        with self.assertRaises(PermissionDenied): resolve_token('A' * 43, NS(pk=1), self.actor({'dic.can_view_dic_operations', 'dic.can_view_dic_ids'}))
        ids.objects.filter.assert_not_called()

    @patch('dic_movement.services.eligibility', return_value={'eligible': True})
    @patch('dic_movement.services.DigitalIDIssue')
    def test_valid_token_is_digest_scoped_to_edition_and_live_issue(self, ids, eligible):
        edition = NS(pk=1); enrollment = NS(pk=uuid4())
        ids.objects.filter.return_value.select_related.return_value.first.return_value = NS(enrollment=enrollment)
        self.assertIs(resolve_token('A' * 43, edition, self.actor()), enrollment)
        filters = ids.objects.filter.call_args.kwargs
        self.assertEqual(filters['enrollment__edition'], edition)
        self.assertTrue(filters['revoked_at__isnull'])
        self.assertIn('expires_at__gt', filters)
        self.assertNotEqual(filters['verification_digest'], 'A' * 43)

    @patch('dic_movement.services.eligibility', return_value={'eligible': False})
    @patch('dic_movement.services.DigitalIDIssue')
    def test_expired_revoked_foreign_or_ineligible_id_denied(self, ids, eligible):
        query = ids.objects.filter.return_value.select_related.return_value
        for value in [None, NS(enrollment=NS(pk=uuid4()))]:
            query.first.return_value = value
            with self.assertRaises(ValidationError): resolve_token('A' * 43, NS(pk=1), self.actor())

    def test_presence_and_transition_matrix(self):
        self.assertEqual(presence(False, None), 'not_arrived')
        self.assertEqual(presence(True, None), 'inside')
        self.assertEqual(presence(True, 'departure'), 'outside')
        self.assertEqual(presence(True, 'return'), 'inside')
        for state in ['not_arrived', 'inside', 'outside']:
            for action in ['departure', 'return', 'arrive']:
                if (state, action) in [('inside', 'departure'), ('outside', 'return')]: validate_transition(state, action)
                else:
                    with self.assertRaises(ValidationError): validate_transition(state, action)

    def test_departure_needs_explicit_separate_authority_and_reference(self):
        with self.assertRaises(PermissionDenied): departure_authority(self.actor(BASE | {'dic_movement.can_record_movements'}), self.payload())
        for fields in [dict(authorization_checked=False), dict(authorization_reference=''), dict(authorization_reference='x' * 161)]:
            payload = self.payload(); payload.update(fields)
            with self.assertRaises(ValidationError): departure_authority(self.actor(), payload)

    @patch('dic_movement.api.scan_arrival')
    @patch('dic_movement.api.require_checkin_storage')
    @patch('dic_movement.api.resolve_token', return_value=NS(participant_id=uuid4()))
    @patch('dic_movement.api.edition_from', return_value=NS(pk=1))
    def test_arrival_endpoint_returns_saved_original_time_and_duplicate_status(self, edition, resolve, storage, arrive):
        row = NS(checked_in_at=timezone.now(), checked_in_by=NS(get_full_name=lambda: 'Test officer'))
        for created in [True, False]:
            arrive.return_value = (row, created)
            result = self.request(ScanView, self.actor(), data={'action': 'arrive', 'confirmed': True, 'token': 'A' * 43})
            self.assertEqual(result.status_code, 201 if created else 200)
            self.assertEqual(result.data['check_in']['time'], row.checked_in_at.isoformat())

    @patch('dic_movement.services.check_in_participant')
    @patch('dic_movement.services.lock_person')
    @patch('dic_movement.services.resolve_token')
    def test_scan_arrival_revalidates_under_lock_and_reuses_existing_service(self, resolve, lock, arrive):
        enrollment = NS(participant_id=uuid4()); resolve.return_value = enrollment
        actor = self.actor(); edition = NS(pk=1)
        scan_arrival.__wrapped__(edition, 'A' * 43, actor)
        self.assertEqual(resolve.call_count, 2)
        lock.assert_called_once_with(edition, enrollment.participant_id)
        arrive.assert_called_once_with(edition, enrollment.participant_id, actor)

    @patch('dic_movement.services.DICAdminAuditEvent')
    @patch('dic_movement.services.Movement')
    @patch('dic_movement.services.snapshot', return_value={'presence': 'inside', 'version': 0})
    @patch('dic_movement.services.lock_person')
    @patch('dic.models.CampEnrollment.objects')
    def test_movement_create_audits_actor_identity_and_edition(self, enrollments, lock, snapshot, movements, audits):
        enrollments.filter.return_value.first.return_value = None
        movements.objects.filter.return_value.first.return_value = None
        movements.objects.create.return_value = NS(pk=uuid4(), sequence=1)
        actor = self.actor(); edition = NS(pk=1); participant_id = uuid4()
        row, created = record_movement.__wrapped__(edition, participant_id, actor, self.payload())
        enrollments.filter.assert_called_once_with(edition=edition, participant_id=participant_id)
        self.assertTrue(created)
        self.assertEqual(movements.objects.create.call_args.kwargs['recorded_by'], actor)
        self.assertEqual(audits.objects.create.call_args.kwargs['details']['participant'], str(participant_id))
        self.assertEqual(audits.objects.create.call_args.kwargs['details']['edition'], edition.pk)

    @patch('dic_movement.services.Movement')
    @patch('dic_movement.services.snapshot', return_value={'presence': 'inside', 'version': 1})
    @patch('dic_movement.services.lock_person')
    @patch('dic.models.CampEnrollment.objects')
    def test_stale_version_rejected_without_write(self, enrollments, lock, snapshot, movements):
        enrollments.filter.return_value.first.return_value = None
        movements.objects.filter.return_value.first.return_value = None
        with self.assertRaises(ValidationError): record_movement.__wrapped__(NS(pk=1), uuid4(), self.actor(), self.payload())
        movements.objects.create.assert_not_called()

    @patch('dic_movement.services.DICAdminAuditEvent')
    @patch('dic_movement.services.Movement')
    @patch('dic_movement.services.lock_person')
    def test_exact_request_replay_does_not_duplicate_or_audit(self, lock, movements, audits):
        person = uuid4(); payload = self.payload()
        row = NS(participant_id=person, kind='departure', recorded_by_id=7, reason='', authorization_reference=payload['authorization_reference'])
        movements.objects.filter.return_value.first.return_value = row
        self.assertEqual(record_movement.__wrapped__(NS(pk=1), person, self.actor(), payload), (row, False))
        movements.objects.create.assert_not_called(); audits.objects.create.assert_not_called()
        with self.assertRaises(ValidationError): record_movement.__wrapped__(NS(pk=1), uuid4(), self.actor(), payload)
