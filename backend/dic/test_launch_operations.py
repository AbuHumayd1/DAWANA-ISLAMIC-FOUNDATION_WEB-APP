"""Database-free policy/adapter tests; run with the dummy-database policy harness.

ORM writes/locks are isolated in these tests. They do not certify actual database
constraints or PostgreSQL interleavings; those require isolated acceptance.
"""
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from uuid import uuid4
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied as ModelPermissionDenied, ValidationError as ModelValidationError
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from . import launch_management as service, launch_operations_api as api
from .models import AcademicClass, AcademicAssignment, CampAnnouncement, CampEdition


def staff(*permissions, active=True, is_staff=True):
    return NS(pk=7, is_authenticated=True, is_active=active, is_staff=is_staff,
        is_superuser=False, has_perm=lambda value: value in {'dic.' + p for p in permissions},
        get_username=lambda: 'synthetic-operator')


class LaunchOperationsPolicyTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.edition = CampEdition(pk=41, name='Synthetic camp', year=2098)

    def request(self, view, user, method='get', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/?edition=41', data or {}, format='json')
        if user is not None:
            force_authenticate(request, user=user)
        return view.as_view()(request, **kwargs)

    def test_all_editor_urls_reject_missing_inactive_nonstaff_and_unprivileged_before_storage(self):
        for view, kwargs in ((api.OperationsClassesView, {}), (api.OperationsClassDetailView, {'class_id': 1}),
                (api.OperationsAssignmentsView, {}), (api.OperationsAnnouncementsView, {}),
                (api.OperationsAnnouncementDetailView, {'announcement_id': 1}),
                (api.OperationsAnnouncementPublicationView, {'announcement_id': 1}),
                (api.OperationsLaunchHistoryView, {'domain': 'announcements'})):
            for user in (None, AnonymousUser(), staff('can_view_dic_operations'),
                    staff('can_view_dic_operations', 'manage_dic_classes', 'manage_dic_announcements', active=False),
                    staff('can_view_dic_operations', 'manage_dic_classes', 'manage_dic_announcements', is_staff=False)):
                with self.subTest(view=view.__name__, user=user), patch.object(api, 'require_launch_storage') as storage:
                    self.assertEqual(self.request(view, user, 'post', **kwargs).status_code, 403)
                    storage.assert_not_called()

    def test_session_write_requires_csrf(self):
        request = APIRequestFactory(enforce_csrf_checks=True).post('/?edition=41', {}, format='json')
        request.user = staff('can_view_dic_operations', 'manage_dic_classes')
        with patch.object(api, 'require_launch_storage') as storage:
            response = api.OperationsClassesView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn('CSRF', str(response.data))
        storage.assert_not_called()

    def test_explicit_edition_is_mandatory(self):
        for query in ({}, {'edition': '-1'}, {'edition': 'another'}, {'edition': '0'}):
            with self.subTest(query=query), patch.object(api.CampEdition, 'objects') as editions:
                with self.assertRaises(ValidationError):
                    api.edition_for(NS(query_params=query))
                editions.get.assert_not_called()

    def test_authorized_class_list_scopes_edition_counts_and_minimal_fields(self):
        row = AcademicClass(pk=1, edition=self.edition, name='Approved class', updated_at=self.now)
        row.assigned_count = 4
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api.AcademicClass, 'objects') as classes:
            classes.filter.return_value.annotate.return_value.order_by.return_value = [row]
            response = self.request(api.OperationsClassesView, staff('can_view_dic_operations', 'manage_dic_classes'))
        self.assertEqual(response.status_code, 200)
        classes.filter.assert_called_once_with(edition=self.edition)
        self.assertEqual(response.data['results'][0]['assigned_count'], 4)
        self.assertEqual(set(response.data['results'][0]), {'id', 'name', 'active', 'version', 'assigned_count'})
        self.assertIn('no-store', response['Cache-Control'])

    def test_class_create_and_edit_delegate_to_shared_service(self):
        actor = staff('can_view_dic_operations', 'manage_dic_classes')
        def saved(row, user, **kwargs):
            row.pk = 1
            row.updated_at = self.now
            return row
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api, 'save_academic', side_effect=saved) as save:
            response = self.request(api.OperationsClassesView, actor, 'post', dict(name='New class', active=True))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(save.call_args.args[0].edition_id, 41)
        row = AcademicClass(pk=1, edition=self.edition, name='Old', updated_at=self.now)
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api.AcademicClass, 'objects') as classes, patch.object(api, 'save_academic', side_effect=saved) as save:
            classes.filter.return_value.first.return_value = row
            response = self.request(api.OperationsClassDetailView, actor, 'post',
                dict(name='Renamed', active=False, version=self.now.isoformat()), class_id=1)
        self.assertEqual(response.status_code, 200)
        classes.filter.assert_called_once_with(pk=1, edition=self.edition)
        self.assertEqual(save.call_args.kwargs['expected'], self.now.isoformat())

    def test_unknown_fields_and_missing_update_tokens_are_rejected(self):
        for form, values in ((api.ClassInput, dict(name='Class', active=True, edition=999)),
                (api.DraftInput, dict(title='Draft', body='Text', starts_at=None, ends_at=None, audience='public')),
                (api.PublicationInput, dict(action='approve', version='v', reason='review'))):
            self.assertFalse(form(data=values).is_valid())
        with self.assertRaises(ValidationError):
            api.require_version({})

    def test_strict_inputs_expose_mapping_errors_in_both_validation_modes(self):
        expected = {api_settings.NON_FIELD_ERRORS_KEY: ['Only the documented fields are accepted.']}
        for form in (api.ClassInput, api.AssignmentInput, api.DraftInput, api.PublicationInput):
            for payload in ({'unexpected': True}, [], 'not an object', 42):
                for raising in (False, True):
                    with self.subTest(form=form.__name__, payload=payload, raising=raising):
                        serializer = form(data=payload)
                        if raising:
                            with self.assertRaises(ValidationError) as error:
                                serializer.is_valid(raise_exception=True)
                            self.assertEqual(error.exception.detail, expected)
                        else:
                            self.assertFalse(serializer.is_valid())
                        self.assertEqual(serializer.errors, expected)
                        self.assertEqual(serializer.validated_data, {})

    def test_malformed_editor_requests_return_400_without_service_writes(self):
        actor = staff('can_view_dic_operations', 'manage_dic_classes',
            'manage_dic_announcements', 'publish_dic_announcements')
        # Keep real permission/validation/response handling while excluding only
        # the transaction entry that requires PostgreSQL (covered by DB tests).
        class AssignmentAdapter(api.OperationsAssignmentsView):
            post = api.OperationsAssignmentsView.post.__wrapped__

        cases = (
            (api.OperationsClassesView, {}, {'name': 'Class', 'active': True, 'edition': 999}, 'save_academic'),
            (api.OperationsClassesView, {}, [], 'save_academic'),
            (api.OperationsClassesView, {}, 'invalid object', 'save_academic'),
            (api.OperationsClassesView, {}, {'name': [], 'active': {}}, 'save_academic'),
            (api.OperationsClassDetailView, {'class_id': 1}, {'name': 'Class', 'active': True}, 'save_academic'),
            (AssignmentAdapter, {}, {'participant': 'not-a-uuid', 'academic_class': 1, 'reason': 'Review'}, 'save_academic'),
            (AssignmentAdapter, {}, {'participant': str(uuid4()), 'academic_class': 'invalid', 'reason': 'Review'}, 'save_academic'),
            (AssignmentAdapter, {}, {'participant': str(uuid4()), 'academic_class': 0, 'reason': 'Review'}, 'save_academic'),
            (api.OperationsAnnouncementsView, {}, {'title': 'Draft', 'body': 'Text', 'starts_at': None, 'ends_at': None, 'status': 'published'}, 'save_announcement_draft'),
            (api.OperationsAnnouncementsView, {}, {'title': [], 'body': {}, 'starts_at': 'invalid', 'ends_at': None}, 'save_announcement_draft'),
            (api.OperationsAnnouncementsView, {}, {'title': 'Draft', 'body': 'Text', 'starts_at': self.now.isoformat(), 'ends_at': self.now.isoformat()}, 'save_announcement_draft'),
            (api.OperationsAnnouncementPublicationView, {'announcement_id': 1}, {'action': 'approve', 'version': 'v', 'reason': 'Review'}, 'publish_announcement'),
        )
        for view, kwargs, payload, service_name in cases:
            with self.subTest(view=view.__name__, payload=payload), \
                    patch.object(api, 'require_launch_storage'), patch.object(api, service_name) as write:
                request = APIRequestFactory().post('/?edition=41', payload, format='json')
                force_authenticate(request, user=actor)
                response = view.as_view()(request, **kwargs)
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.data, (dict, list))
                self.assertTrue(response.data)
                response.render()  # Exercise the error response, not only is_valid().
                write.assert_not_called()

    def test_assignment_model_errors_and_edit_conflicts_remain_client_responses(self):
        # Preserve the service-to-API error contract without ORM writes.
        for error, expected in ((ModelValidationError({'participant': ['Registration required.']}), 400),
                (service.StaleLaunchRecord('Reload this assignment.'), 409),
                (api.IntegrityError('PRIVATE DATABASE DETAIL'), 409)):
            with self.subTest(error=type(error).__name__), \
                    patch.object(api, 'save_academic', side_effect=error) as write:
                with self.assertRaises((ValidationError, api.Conflict)) as caught:
                    api.call_service(write, AcademicAssignment(), staff('manage_dic_classes'))
                self.assertEqual(caught.exception.status_code, expected)
                self.assertNotIn('PRIVATE DATABASE', str(caught.exception.detail))

    def test_stale_class_and_announcement_edits_return_409(self):
        actor = staff('can_view_dic_operations', 'manage_dic_classes', 'manage_dic_announcements')
        cases = (
            (api.OperationsClassDetailView, {'class_id': 1}, api.AcademicClass,
                {'name': 'Class', 'active': True, 'version': 'stale'}, 'save_academic'),
            (api.OperationsAnnouncementDetailView, {'announcement_id': 1}, api.CampAnnouncement,
                {'title': 'Draft', 'body': 'Text', 'starts_at': None, 'ends_at': None, 'version': 'stale'}, 'save_announcement_draft'),
        )
        for view, kwargs, model, payload, service_name in cases:
            with self.subTest(view=view.__name__), patch.object(api, 'require_launch_storage'), \
                    patch.object(api, 'edition_for', return_value=self.edition), \
                    patch.object(model, 'objects') as rows, \
                    patch.object(api, service_name, side_effect=service.StaleLaunchRecord('Reload.')):
                rows.filter.return_value.first.return_value = model(pk=1, edition=self.edition)
                response = self.request(view, actor, 'post', payload, **kwargs)
                self.assertEqual(response.status_code, 409)
                self.assertIn('Reload', str(response.data))
                response.render()

    def test_editor_cannot_publish_even_with_operations_access(self):
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'publish_announcement') as publish:
            response = self.request(api.OperationsAnnouncementPublicationView,
                staff('can_view_dic_operations', 'manage_dic_announcements'), 'post',
                dict(action='publish', version='v', reason='review'), announcement_id=1)
        self.assertEqual(response.status_code, 403)
        publish.assert_not_called()

    def test_publisher_cannot_create_or_edit_drafts(self):
        for view, kwargs in ((api.OperationsAnnouncementsView, {}), (api.OperationsAnnouncementDetailView, {'announcement_id': 1})):
            with patch.object(api, 'require_launch_storage'), patch.object(api, 'save_announcement_draft') as save:
                response = self.request(view, staff('can_view_dic_operations', 'publish_dic_announcements'), 'post',
                    dict(title='Draft', body='Text', starts_at=None, ends_at=None), **kwargs)
            self.assertEqual(response.status_code, 403)
            save.assert_not_called()

    def test_announcement_draft_create_is_always_a_draft(self):
        def saved(row, user, **kwargs):
            row.pk, row.updated_at = 3, self.now
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api, 'save_announcement_draft', side_effect=saved) as save:
            response = self.request(api.OperationsAnnouncementsView,
                staff('can_view_dic_operations', 'manage_dic_announcements'), 'post',
                dict(title='Private draft', body='Only authorized staff see this', starts_at=None, ends_at=None))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(save.call_args.args[0].edition_id, 41)

    def test_announcement_directory_scopes_edition_and_rejects_invented_audiences(self):
        actor = staff('can_view_dic_operations', 'publish_dic_announcements')
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api.CampAnnouncement, 'objects') as announcements:
            announcements.filter.return_value.order_by.return_value = []
            response = self.request(api.OperationsAnnouncementsView, actor)
        self.assertEqual(response.status_code, 200)
        announcements.filter.assert_called_once_with(edition=self.edition)
        self.assertEqual(response.data['results'], [])
        with patch.object(api, 'edition_for', return_value=self.edition), patch.object(api.CampAnnouncement, 'objects'):
            with self.assertRaises(ValidationError):
                api.OperationsAnnouncementsView().get(NS(query_params={'edition': '41', 'audience': 'public'}))

    def test_cross_edition_detail_is_unavailable_without_service_write(self):
        actor = staff('can_view_dic_operations', 'manage_dic_announcements')
        with patch.object(api, 'require_launch_storage'), patch.object(api, 'edition_for', return_value=self.edition), \
                patch.object(api.CampAnnouncement, 'objects') as announcements, patch.object(api, 'save_announcement_draft') as save:
            announcements.filter.return_value.first.return_value = None
            response = self.request(api.OperationsAnnouncementDetailView, actor, 'post',
                dict(title='Other edition', body='Text', starts_at=None, ends_at=None, version='v'), announcement_id=999)
        self.assertEqual(response.status_code, 404)
        announcements.filter.assert_called_once_with(pk=999, edition=self.edition)
        save.assert_not_called()

    def test_camper_updates_keep_edition_draft_and_visibility_window_filters(self):
        from .launch_api import CampUpdatesView
        item = NS(order=NS(edition=self.edition, registration_basis='paid'), participant_id=uuid4())
        with patch('dic.launch_api.portal_item', return_value=item), patch('dic.launch_api.connection') as connection, \
                patch('dic.launch_api.CampAnnouncement.objects') as announcements, \
                patch('dic.launch_api.assigned_class', return_value={'status': 'unassigned'}), \
                patch('dic.launch_api.timezone.now', return_value=self.now):
            connection.introspection.table_names.return_value = [CampAnnouncement._meta.db_table]
            announcements.filter.return_value.filter.return_value.filter.return_value = []
            response = CampUpdatesView().get(NS(query_params={'item_id': '4', 'edition': '999'}))
        announcements.filter.assert_called_once_with(edition=self.edition, status='published')
        starts = announcements.filter.return_value.filter.call_args.args[0]
        ends = announcements.filter.return_value.filter.return_value.filter.call_args.args[0]
        self.assertEqual(starts.connector, 'OR')
        self.assertIn(('starts_at__lte', self.now), starts.children)
        self.assertIn(('ends_at__gt', self.now), ends.children)
        self.assertEqual(response.data['announcements'], [])

    def test_missing_class_projection_is_explicit_and_never_materializes_assignments(self):
        from .launch_services import assigned_class
        with patch('dic.launch_services.connection') as connection, patch('dic.launch_services.AcademicAssignment.objects') as assignments:
            connection.introspection.table_names.return_value = []
            self.assertEqual(assigned_class(uuid4(), self.edition)['status'], 'pending_setup')
            assignments.create.assert_not_called()
        with patch('dic.launch_services.connection') as connection, patch('dic.launch_services.AcademicAssignment.objects') as assignments:
            connection.introspection.table_names.return_value = [AcademicClass._meta.db_table, AcademicAssignment._meta.db_table]
            assignments.select_related.return_value.filter.return_value.first.return_value = None
            self.assertEqual(assigned_class(uuid4(), self.edition)['status'], 'unassigned')
            assignments.create.assert_not_called()

    def test_announcement_time_windows_and_state_are_distinct(self):
        for status, starts, ends, expected in (
                ('draft', None, None, 'draft'), ('published', self.now + timedelta(hours=1), None, 'scheduled'),
                ('published', None, self.now - timedelta(seconds=1), 'expired'), ('published', None, None, 'visible')):
            row = CampAnnouncement(pk=1, edition=self.edition, title='Test', body='Text',
                status=status, starts_at=starts, ends_at=ends, updated_at=self.now)
            with patch.object(api.timezone, 'now', return_value=self.now):
                self.assertEqual(api.announcement_row(row)['visibility'], expected)
        self.assertFalse(api.DraftInput(data=dict(title='Test', body='Text',
            starts_at=self.now.isoformat(), ends_at=self.now.isoformat())).is_valid())

    def test_history_authorization_uses_url_domain(self):
        with patch.object(api, 'require_launch_storage') as storage:
            response = self.request(api.OperationsLaunchHistoryView,
                staff('can_view_dic_operations', 'manage_dic_classes'), domain='announcements')
        self.assertEqual(response.status_code, 403)
        storage.assert_not_called()

    def test_error_adapter_returns_conflict_without_raw_database_details(self):
        with self.assertRaises(api.Conflict):
            api.call_service(Mock(side_effect=service.StaleLaunchRecord('Changed.')))
        with self.assertRaises(api.Conflict) as error:
            api.call_service(Mock(side_effect=api.IntegrityError('PRIVATE DATABASE DETAIL')))
        self.assertNotIn('PRIVATE', str(error.exception))


class LaunchManagementServiceTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        from django.contrib.auth import get_user_model
        self.actor = get_user_model()(pk=7, username='synthetic-operator', is_active=True, is_staff=True)
        self.actor.has_perm = lambda value: value in {'dic.manage_dic_classes', 'dic.manage_dic_announcements', 'dic.publish_dic_announcements'}
        self.edition = CampEdition(pk=41, name='Synthetic camp')

    def test_permission_is_checked_before_locks_or_writes(self):
        for permission in ('manage_dic_classes', 'manage_dic_announcements', 'publish_dic_announcements'):
            for actor in (staff(), staff(permission, active=False), staff(permission, is_staff=False)):
                with self.assertRaises(ModelPermissionDenied):
                    service.require_launch_permission(actor, permission)

    def test_stale_version_rejects_concurrent_modification(self):
        row = AcademicClass(updated_at=self.now)
        with self.assertRaises(service.StaleLaunchRecord):
            service.check_version(row, (self.now - timedelta(seconds=1)).isoformat())
        service.check_version(row, self.now.isoformat())

    def test_class_edit_locks_edition_then_record_and_preserves_before_after(self):
        previous = AcademicClass(pk=1, edition=self.edition, name='Original', active=True, updated_at=self.now)
        row = AcademicClass(pk=1, edition=self.edition, name='Renamed', active=False, updated_at=self.now)
        order = []
        with patch.object(service.CampEdition, 'objects') as editions, patch.object(service.AcademicClass, 'objects') as classes, \
                patch.object(row, 'full_clean') as validate, patch.object(row, 'save'), patch.object(service, 'audit_launch') as audit:
            editions.select_for_update.return_value.get.side_effect = lambda **kw: order.append('edition')
            classes.select_for_update.return_value.get.side_effect = lambda **kw: (order.append('record'), previous)[1]
            service.save_academic.__wrapped__(row, self.actor, expected=self.now.isoformat())
        self.assertEqual(order, ['edition', 'record'])
        validate.assert_called_once()
        self.assertEqual(audit.call_args.args[3], dict(name='Original', active=True))
        self.assertFalse(row.active)

    def test_duplicate_assignment_is_not_silently_transferred(self):
        row = AcademicAssignment(edition=self.edition, participant_id=uuid4(), academic_class_id=2)
        with patch.object(service.CampEdition, 'objects'), patch.object(service.AcademicAssignment, 'objects') as assignments, \
                patch.object(row, 'save') as save, patch.object(service, 'audit_launch') as audit:
            assignments.filter.return_value.exists.return_value = True
            with self.assertRaises(service.StaleLaunchRecord):
                service.save_academic.__wrapped__(row, self.actor)
        save.assert_not_called(); audit.assert_not_called()

    def test_transfer_retains_assignment_identity_and_audits_old_class(self):
        person = uuid4()
        old_class = AcademicClass(pk=1, edition=self.edition, name='Original')
        target = AcademicClass(pk=2, edition=self.edition, name='Destination')
        old = AcademicAssignment(pk=9, edition=self.edition, participant_id=person, academic_class=old_class, updated_at=self.now)
        row = AcademicAssignment(pk=9, edition=self.edition, participant_id=person, academic_class=target, updated_at=self.now)
        with patch.object(service.CampEdition, 'objects'), patch.object(service.AcademicAssignment, 'objects') as assignments, \
                patch.object(row, 'full_clean'), patch.object(row, 'save') as save, patch.object(service, 'audit_launch') as audit:
            assignments.select_for_update.return_value.get.return_value = old
            service.save_academic.__wrapped__(row, self.actor, expected=self.now.isoformat(), reason='Reviewed transfer')
        self.assertEqual(row.pk, 9); self.assertEqual(row.participant_id, person)
        self.assertEqual(audit.call_args.args[3]['academic_class'], 1)
        self.assertEqual(audit.call_args.args[3]['class_name'], 'Original')
        self.assertEqual(audit.call_args.args[4], 'Reviewed transfer')
        save.assert_called_once()

    def test_cross_edition_edit_rejected(self):
        row = AcademicClass(pk=1, edition_id=42, name='Moved', updated_at=self.now)
        old = AcademicClass(pk=1, edition_id=41, name='Original', updated_at=self.now)
        with patch.object(service.CampEdition, 'objects'), patch.object(service.AcademicClass, 'objects') as classes, patch.object(row, 'save') as save:
            classes.select_for_update.return_value.get.return_value = old
            with self.assertRaises(ModelValidationError):
                service.save_academic.__wrapped__(row, self.actor, expected=self.now.isoformat())
        save.assert_not_called()

    def test_invalid_participant_and_inactive_cross_edition_classes_use_existing_validator(self):
        target = AcademicClass(pk=1, edition_id=41, name='Class', active=True)
        for edition, active in ((42, True), (41, False)):
            target.active = active
            with self.assertRaises(ModelValidationError):
                AcademicAssignment(edition_id=edition, academic_class=target).clean()
        target.active = True
        with patch('dic.models.RegistrationOrderItem.objects') as items:
            items.filter.return_value.exclude.return_value.exists.return_value = False
            with self.assertRaises(ModelValidationError):
                AcademicAssignment(edition_id=41, participant_id=uuid4(), academic_class=target).clean()
            items.filter.return_value.exclude.assert_called_once_with(order__registration_basis='tutor')

    def test_publish_and_withdraw_are_explicit_audited_transitions(self):
        row = CampAnnouncement(pk=3, edition=self.edition, title='Approved', body='Content', updated_at=self.now)
        for action, status, event in (('publish', 'published', 'announcement_published'), ('withdraw', 'draft', 'announcement_unpublished')):
            with patch.object(service.CampEdition, 'objects') as editions, patch.object(service.CampAnnouncement, 'objects') as announcements, \
                    patch.object(row, 'save') as save, patch.object(service, 'audit_launch') as audit:
                announcements.select_for_update.return_value.get.return_value = row
                service.publish_announcement.__wrapped__(41, 3, self.actor, action, expected=self.now.isoformat(), reason='Reviewed')
            editions.select_for_update.return_value.get.assert_called_once_with(pk=41)
            announcements.select_for_update.return_value.get.assert_called_once_with(pk=3, edition_id=41)
            self.assertEqual(row.status, status)
            self.assertEqual(audit.call_args.args[2], event)
            save.assert_called_once()

    def test_invalid_publication_transition_and_stale_draft_do_not_save(self):
        row = CampAnnouncement(pk=3, edition=self.edition, title='Approved', body='Content', status='published', updated_at=self.now)
        with patch.object(service.CampEdition, 'objects'), patch.object(service.CampAnnouncement, 'objects') as announcements, patch.object(row, 'save') as save:
            announcements.select_for_update.return_value.get.return_value = row
            with self.assertRaises(ModelValidationError):
                service.publish_announcement.__wrapped__(41, 3, self.actor, 'publish')
            with self.assertRaises(ModelValidationError):
                service.save_announcement_draft.__wrapped__(row, self.actor, expected=self.now.isoformat())
        save.assert_not_called()


class LaunchMigrationParityTests(SimpleTestCase):
    def test_model_state_matches_source_migrations_without_a_database(self):
        from django.apps import apps
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.state import ProjectState
        from django.db.migrations.autodetector import MigrationAutodetector
        from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
        loader = MigrationLoader(None, ignore_no_migrations=True)
        loader.graph.validate_consistency()
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps),
            NonInteractiveMigrationQuestioner(dry_run=True, verbosity=0)).changes(graph=loader.graph)
        self.assertEqual(changes, {}, 'Source model/migration drift; review without applying migrations.')
