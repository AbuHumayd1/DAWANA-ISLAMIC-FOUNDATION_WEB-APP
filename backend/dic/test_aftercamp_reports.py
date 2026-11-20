"""Contracts for permission-scoped, evidence-backed after-camp reporting."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.template.loader import render_to_string
from rest_framework.exceptions import PermissionDenied
from docx import Document

from dic import aftercamp_reports as reports


class AfterCampReportingTests(SimpleTestCase):
    def setUp(self):
        self.edition = SimpleNamespace(
            pk=1, name='Synthetic camp', camp_start_date='2038-12-23',
            camp_end_date='2039-01-01')
        self.actor = SimpleNamespace(has_perm=lambda permission: permission != 'dic_finance.can_export_finance')

    def test_permission_redaction_is_explicit_and_no_private_rows_escape(self):
        evidence = {
            'available': True,
            'metrics': [{'label': 'Registered participants', 'value': 7, 'unit': 'count'},
                        {'label': 'Bookings', 'value': 5, 'unit': 'count'},
                        {'label': 'Regular campers', 'value': 6, 'unit': 'count'},
                        {'label': 'Tutor participants', 'value': 1, 'unit': 'count'},
                        {'label': 'Confirmed bookings', 'value': 4, 'unit': 'count'}],
            'series': {'Registration categories': [
                {'label': 'Primary', 'value': 4},
                {'label': 'Secondary', 'value': 2}]},
            'rows': [{'participant_name': 'PRIVATE NAME', 'email': 'private@example.test'}],
            'notes': [],
        }
        with patch.object(reports.reports, 'require_report'), patch.object(
            reports.reports, 'report', return_value=evidence) as get_data, patch(
            'dic.aftercamp_evidence.additional_sections',return_value=[]), patch(
            'dic.aftercamp_evidence.approved_assessments',return_value=[]):
            result = reports.build(self.edition, self.actor, for_download=True)
        registration = next(s for s in result['sections'] if s['domain'] == 'registration')
        finance = next(s for s in result['sections'] if s['domain'] == 'finance')
        self.assertEqual(finance['state'], 'restricted')
        self.assertEqual(registration['state'], 'recorded')
        self.assertIn('7 distinct registered participants', registration['summary'])
        self.assertEqual(registration['charts'][0]['points'][0]['width'], 100)
        self.assertEqual(registration['charts'][0]['points'][1]['width'], 50)
        self.assertNotIn('PRIVATE NAME', str(result))
        self.assertNotIn('private@example.test', str(result))
        self.assertNotIn('finance', [call.args[3] for call in get_data.call_args_list])

    def test_unconfigured_academic_not_invented(self):
        def reply(edition, selected, actor, domain):
            return {'available': False, 'notes': ['No persisted class outcomes'],
                    'metrics': [], 'series': {}, 'rows': []}
        actor = SimpleNamespace(has_perm=lambda permission: True)
        with patch.object(reports.reports, 'require_report'), patch.object(
            reports.reports, 'report', side_effect=reply), patch(
            'dic.aftercamp_evidence.additional_sections',return_value=[]), patch(
            'dic.aftercamp_evidence.approved_assessments',return_value=[]):
            result = reports.build(self.edition, actor)
        self.assertEqual(result['covered_count'], 0)
        self.assertEqual(next(s for s in result['sections'] if s['domain']=='academic')['state'], 'unavailable')
        self.assertIn('Interim snapshot', result['report_status'])

    def test_word_report_has_narrative_charts_and_no_pii(self):
        payload = {
            'edition': {'name': 'Synthetic camp'}, 'generated_at': '2038-12-01T10:00:00+01:00',
            'generated_display': '01 December 2038, 10:00 WAT',
            'report_status': 'Interim snapshot', 'covered_count': 1, 'total_sections': 1,
            'methodology': ['No missing evidence replaced by zero'],
            'sections': [{'domain': 'registration', 'title': 'Participation',
                          'state': 'recorded', 'summary': '7 participants were registered.',
                          'metrics': [{'label': 'Registered participants', 'display': '7'}],
                          'charts': [{'title': 'Registration categories',
                                      'points': [{'label': 'Primary', 'value': 4, 'display': '4'},
                                                 {'label': 'Secondary', 'value': 2, 'display': '2'}]}],
                          'notes': ['Active registrations only']}],
        }
        content = reports.export_word(payload)
        document = Document(BytesIO(content))
        text = '\n'.join(p.text for p in document.paragraphs)
        self.assertIn('Executive overview', text)
        self.assertIn('7 participants were registered.', text)
        self.assertTrue(document.inline_shapes)
        html = render_to_string('dic/aftercamp_reporting.html', {'report': payload})
        self.assertIn('Camp performance report', html)
        self.assertNotIn('<table', html)

    def test_extra_sections_accept_screen_and_export_modes_without_500(self):
        from dic import aftercamp_evidence
        actor = SimpleNamespace(has_perm=lambda permission: False)
        with patch.object(aftercamp_evidence.reports, 'storage', return_value=False):
            for download in (False, True):
                sections = aftercamp_evidence.additional_sections(
                    self.edition, actor, for_download=download)
                self.assertTrue(isinstance(sections, list))
                self.assertTrue(any(section['domain'] == 'programme'
                                    for section in sections))

    def test_comprehensive_report_excludes_attempts_and_hypothetical_booking_value(self):
        finance = {'available': True, 'metrics': [
            {'label': 'Expected booking value', 'value': 13000000, 'unit': 'NGN kobo'},
            {'label': 'Gross verified collections', 'value': 400000, 'unit': 'NGN kobo'},
            {'label': 'Applied recorded adjustments', 'value': 0, 'unit': 'NGN kobo'},
            {'label': 'Net verified collections', 'value': 400000, 'unit': 'NGN kobo'},
            {'label': 'Pending attempts', 'value': 4, 'unit': 'count'},
            {'label': 'Failed attempts', 'value': 0, 'unit': 'count'},
            {'label': 'Exceptional attempts', 'value': 5, 'unit': 'count'},
        ], 'series': {}, 'notes': [], 'rows': []}
        actor = SimpleNamespace(has_perm=lambda permission: True)
        with patch.object(reports.reports, 'require_report'), patch.object(
            reports.reports, 'report', return_value=finance), patch(
            'dic.aftercamp_evidence.additional_sections', return_value=[]), patch(
            'dic.aftercamp_evidence.approved_assessments', return_value=[]):
            for download in (False, True):
                result = reports.build(self.edition, actor, for_download=download)
                section = next(s for s in result['sections'] if s['domain'] == 'finance')
                labels = {m['label'] for m in section['metrics']}
                self.assertIn('Gross verified collections', labels)
                self.assertIn('Net verified collections', labels)
                self.assertNotIn('Expected booking value', labels)
                self.assertNotIn('Pending attempts', labels)
                self.assertNotIn('Failed attempts', labels)
                self.assertNotIn('Exceptional attempts', labels)

    def test_finance_kobo_converts_to_naira_and_missing_is_not_zero(self):
        self.assertEqual(reports.display(100050, 'NGN kobo'), '₦1,000.50')
        self.assertEqual(reports.display(None), 'Unavailable')
        self.assertIn('not proof of bank settlement', reports.summarize('finance', [
            {'label': 'Gross verified collections', 'display': '₦1,000'},
            {'label': 'Applied recorded adjustments', 'display': '₦100'},
            {'label': 'Net verified collections', 'display': '₦900'},
        ]))
