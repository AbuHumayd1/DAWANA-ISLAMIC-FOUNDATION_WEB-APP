"""Database-free contract tests; the consolidated runner forbids DB connections."""
from datetime import date, datetime, time, timezone as utc
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from .models import TimetableEntry
from .timetable_admin import TimetableEntryAdmin
from .timetable_services import dates_for, selected_date, require_staff, validate_day, publish_days
from .management.commands.import_dic2026_timetables import source_rows, import_rows, Command


class TimetablePolicyTests(SimpleTestCase):
    def setUp(self):
        self.edition = SimpleNamespace(pk=9, camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1))
        self.data = source_rows()

    def test_exactly_two_types_and_all_ten_dates(self):
        self.assertEqual(set(dict(TimetableEntry.TYPES)), {'activities', 'food'})
        for kind in ('activities', 'food'):
            rows = [r for r in self.data['entries'] if r['timetable_type'] == kind]
            self.assertEqual(set(r['date'] for r in rows), set(dates_for(self.edition)))
            for row in rows:
                self.assertEqual(row['day_number'], (row['date'] - self.edition.camp_start_date).days + 1)

    def test_day6_confirmed_amendments(self):
        rows = [r for r in self.data['entries'] if r['day_number'] == 6 and r['timetable_type'] == 'activities']
        health = next(r for r in rows if r['description'] == 'Health Forum / Health Symposium')
        sports = next(r for r in rows if r['description'] == 'Sports Activities')
        self.assertEqual((health['start_time'], health['end_time']), (time(11), time(13)))
        self.assertEqual((sports['start_time'], sports['end_time']), (time(17), time(18, 30)))
        self.assertEqual(health['certainty'], 'confirmed')
        self.assertFalse(any('proposed' in r['description'].lower() or 'optional' in r['description'].lower() for r in rows))

    def test_food_incomplete_text_and_periods_are_preserved(self):
        rows = [r for r in self.data['entries'] if r['timetable_type'] == 'food']
        self.assertEqual(len(rows), 30)
        self.assertEqual(sum(not r['description'].strip() for r in rows), 3)
        self.assertTrue(all(r['start_time'] is None and r['end_time'] is None for r in rows))
        self.assertTrue(any(r['description'].strip() == 'white rice/ofada source/fish' for r in rows))
        self.assertTrue(any(r['description'].strip() == 'meshed beans/potatoe' for r in rows))

    def test_arrival_opening_friday_final_night_and_departure(self):
        rows = [r for r in self.data['entries'] if r['timetable_type'] == 'activities']
        self.assertTrue(any(r['day_number'] == 1 and r['start_time'] == time(16, 30) and 'registration' in r['description'] for r in rows))
        self.assertEqual(sum(r['description'] == 'Official Camp Opening Session' for r in rows), 1)
        self.assertTrue(any('Jumu’ah preparation' in r['description'] for r in rows))
        self.assertEqual(sum(r['description'] == 'Final Night' for r in rows), 1)
        self.assertEqual(sum(r['day_number'] == 10 and r['description'] == 'No scheduled activities' for r in rows), 1)

    def test_sources_have_unique_keys_and_no_overlap(self):
        rows = self.data['entries']
        self.assertEqual(len(rows), len(set(r['source_key'] for r in rows)))
        for day in range(1, 11):
            bounded = [r for r in rows if r['day_number'] == day and r['timetable_type'] == 'activities' and r['start_time'] and r['end_time']]
            for left, right in zip(bounded, bounded[1:]):
                self.assertLessEqual(left['end_time'], right['start_time'])

    def test_pre_camp_defaults_to_next_published_date(self):
        result = selected_date(self.edition, {date(2026, 12, 25)}, now=datetime(2026, 10, 1, tzinfo=utc.utc))
        self.assertEqual(result, date(2026, 12, 25))

    def test_lagos_midnight_and_after_camp_history(self):
        self.assertEqual(selected_date(self.edition, set(), now=datetime(2026, 12, 23, 23, 30, tzinfo=utc.utc)), date(2026, 12, 24))
        self.assertEqual(selected_date(self.edition, {date(2026, 12, 29)}, now=datetime(2027, 1, 9, tzinfo=utc.utc)), date(2026, 12, 29))

    def test_cross_edition_dates_rejected(self):
        with self.assertRaises(ValidationError): selected_date(self.edition, set(), date(2027, 1, 2))
        self.assertEqual(selected_date(self.edition, set(), date(2027, 1, 1)), date(2027, 1, 1))

    def test_staff_permissions_are_separate(self):
        user = Mock(is_active=True, is_staff=True)
        user.has_perm.side_effect = lambda p: p == 'dic.manage_dic_timetables'
        require_staff(user, 'manage_dic_timetables')
        with self.assertRaises(PermissionDenied): require_staff(user, 'publish_dic_timetables')
        user.is_staff = False
        with self.assertRaises(PermissionDenied): require_staff(user, 'manage_dic_timetables')

    def test_admin_drafts_only_and_permission_actions(self):
        admin = TimetableEntryAdmin(TimetableEntry, AdminSite())
        request = SimpleNamespace(user=Mock(is_active=True, is_staff=True))
        request.user.has_perm.side_effect = lambda p: p == 'dic.manage_dic_timetables'
        self.assertTrue(admin.has_change_permission(request, SimpleNamespace(status='draft')))
        self.assertFalse(admin.has_change_permission(request, SimpleNamespace(status='published')))
        request.user.has_perm.side_effect = lambda p: p == 'dic.publish_dic_timetables'
        self.assertTrue(admin.has_view_permission(request))
        self.assertFalse(admin.has_add_permission(request))

    def test_conflicting_ranges_rejected_before_publication(self):
        rows = [Mock(start_time=time(11), end_time=time(13)), Mock(start_time=time(12), end_time=time(14))]
        with self.assertRaises(ValidationError): validate_day(rows)
        rows[1].start_time = time(13)
        validate_day(rows)

    def test_model_rejects_invalid_time_range(self):
        row = TimetableEntry(start_time=time(13), end_time=time(11))
        with self.assertRaises(ValidationError): row.clean()

    def test_model_direct_publication_rejected(self):
        with self.assertRaises(ValidationError): TimetableEntry(status='published').save()

    def test_mixed_edition_publication_rejected_before_locks(self):
        user = Mock(is_active=True, is_staff=True)
        user.has_perm.return_value = True
        queryset = Mock()
        queryset.order_by.return_value.values_list.return_value.distinct.return_value = [(1, 'food'), (2, 'food')]
        with self.assertRaises(ValidationError): publish_days.__wrapped__(user, queryset, True)

    def test_publication_expands_to_complete_day_and_audits(self):
        user = Mock(is_active=True, is_staff=True)
        user.has_perm.return_value = True
        queryset = Mock()
        queryset.order_by.return_value.values_list.side_effect = [
            Mock(distinct=Mock(return_value=[(9, 'food')])),
            Mock(distinct=Mock(return_value=[date(2026, 12, 23)]))]
        rows = [Mock(date=date(2026, 12, 23), start_time=None, end_time=None),
                Mock(date=date(2026, 12, 23), start_time=None, end_time=None)]
        with patch('dic.timetable_services.CampEdition.objects'), patch('dic.timetable_services.TimetableEntry.objects') as entries, patch('dic.timetable_services.DICAdminAuditEvent.objects') as audit:
            entries.select_for_update.return_value.filter.return_value = rows
            self.assertEqual(publish_days.__wrapped__(user, queryset, True), 2)
            entries.select_for_update.return_value.filter.assert_called_once_with(edition_id=9, timetable_type='food', date__in=[date(2026, 12, 23)])
            self.assertTrue(all(r.status == 'published' and r.published_by == user for r in rows))
            self.assertEqual(audit.create.call_args.kwargs['action'], 'timetable_published')

    def test_model_rejects_outside_edition_and_wrong_day_number(self):
        from .models import CampEdition
        edition = CampEdition(pk=9, camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1))
        for day, number in [(date(2027, 1, 2), 11), (date(2026, 12, 24), 9)]:
            with self.subTest(day=day), self.assertRaises(ValidationError):
                TimetableEntry(edition=edition, date=day, day_number=number).clean()

    def test_import_receipt_preserves_staff_edits_and_deletions(self):
        with patch('dic.management.commands.import_dic2026_timetables.DICAdminAuditEvent.objects') as audit, patch('dic.management.commands.import_dic2026_timetables.TimetableEntry.objects') as entries:
            audit.filter.return_value.exists.return_value = True
            self.assertEqual(import_rows(self.edition, Mock(), self.data), 0)
            entries.create.assert_not_called()

    def test_import_creates_drafts_and_never_overwrites_existing_keys(self):
        with patch('dic.management.commands.import_dic2026_timetables.DICAdminAuditEvent.objects') as audit, patch('dic.management.commands.import_dic2026_timetables.TimetableEntry.objects') as entries:
            audit.filter.return_value.exists.return_value = False
            entries.filter.return_value.exists.side_effect = [True] + [False] * (len(self.data['entries']) - 1)
            self.assertEqual(import_rows(self.edition, Mock(), self.data), len(self.data['entries']) - 1)
            self.assertTrue(all(call.kwargs['status'] == 'draft' for call in entries.create.call_args_list))
            entries.update.assert_not_called()
            audit.create.assert_called_once()

    def test_import_preview_does_not_access_database(self):
        Command().handle(edition=9, apply=False)

    def test_portal_requires_authentication_before_storage(self):
        from .timetable_api import ParticipantTimetableView
        from rest_framework.exceptions import AuthenticationFailed
        request = SimpleNamespace(query_params={'item_id': '9'})
        with patch('dic.feedback_services.authorized_grant', side_effect=AuthenticationFailed):
            with self.assertRaises(AuthenticationFailed): ParticipantTimetableView().get(request)

    def test_guardian_scope_rejects_other_booking_items(self):
        from .feedback_services import portal_item
        from rest_framework.exceptions import PermissionDenied as ApiPermissionDenied
        with patch('dic.feedback_services.authorized_grant', return_value=Mock()), patch('dic.feedback_services.scoped_orders', return_value=[SimpleNamespace(pk=42)]), patch('dic.feedback_services.RegistrationOrderItem.objects') as items:
            items.select_related.return_value.filter.return_value.first.return_value = None
            with self.assertRaises(ApiPermissionDenied): portal_item(Mock(), 999)
            self.assertEqual(items.select_related.return_value.filter.call_args.kwargs['order_id__in'], [42])

    def test_portal_filters_published_and_scoped_edition(self):
        from .timetable_api import ParticipantTimetableView
        with patch('dic.timetable_api.portal_item', return_value=SimpleNamespace(order=SimpleNamespace(edition=self.edition))), patch('dic.timetable_api.connection') as connection, patch('dic.timetable_api.TimetableEntry.objects') as entries:
            self.edition.name = 'DIC 2026'
            connection.introspection.table_names.return_value = [TimetableEntry._meta.db_table]
            entries.filter.return_value.values_list.return_value = []
            entries.filter.return_value.filter.return_value = []
            response = ParticipantTimetableView().get(SimpleNamespace(query_params={'item_id': '9', 'edition': '999', 'date': '2026-12-23'}))
            entries.filter.assert_called_once_with(edition=self.edition, timetable_type='activities', status='published')
            self.assertEqual(response.data['entries'], [])
            self.assertEqual(response.data['state'], 'unpublished')

    def test_staff_preview_escapes_untrusted_descriptions(self):
        admin = TimetableEntryAdmin(TimetableEntry, AdminSite())
        obj = Mock(edition='DIC', timetable_type='food', date=date(2026, 12, 23))
        row = SimpleNamespace(time_label='Morning', description='<script>alert(1)</script>', certainty='unspecified', status='draft')
        with patch.object(admin, 'has_view_permission', return_value=True), patch.object(admin, 'get_object', return_value=obj), patch('dic.timetable_admin.TimetableEntry.objects') as entries:
            entries.filter.return_value = [row]
            response = admin.day_preview(APIRequestFactory().get('/'), 1)
            self.assertNotIn(b'<script>', response.content)
            self.assertIn(b'&lt;script&gt;', response.content)
