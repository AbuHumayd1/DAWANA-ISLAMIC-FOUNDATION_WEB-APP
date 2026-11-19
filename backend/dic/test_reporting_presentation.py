"""Reader-facing reporting exports must remain accessible and legible."""
from io import BytesIO
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from dic.reporting_api import presentation_sections
from dic.operations_exports import create_word_report


class ReportingPresentationTests(SimpleTestCase):
    def test_print_report_has_compact_summary_and_readable_detail_panels(self):
        data = {
            'title': 'Registration and demographics',
            'edition': {'name': 'Synthetic 2038'},
            'filters': {}, 'generated_at': '2038-01-01T00:00:00+01:00',
            'scope_label': 'Active registrations', 'available': True,
            'metrics': [{'label': 'Collection', 'value': 123450, 'unit': 'NGN kobo'},
                        {'label': 'Approval', 'value': 50, 'unit': 'percent'},
                        {'label': 'Unknown', 'value': None, 'unit': 'count'}],
            'series': {'Registration categories': [
                {'label': 'Primary', 'value': 4},
                {'label': 'Secondary', 'value': 2}]},
            'rows': [{'label': 'Synthetic', 'status': 'confirmed', 'value': 4}],
            'columns': ['label', 'status', 'value'], 'notes': ['Synthetic source'],
        }
        presentation = presentation_sections(data)
        self.assertEqual(presentation['chart_sections'][0]['points'][0]['width'], 100)
        self.assertEqual(presentation['chart_sections'][0]['points'][1]['width'], 50)
        self.assertEqual(presentation['display_metrics'][0]['display_value'], '₦1,234.50')
        self.assertEqual(presentation['display_metrics'][1]['display_value'], '50.0%')
        self.assertEqual(presentation['display_metrics'][2]['display_value'], 'Unavailable')
        html = render_to_string('dic/reporting.html', {'data': data, **presentation})
        self.assertIn('At a glance', html)
        self.assertIn('₦1,234.50', html)
        self.assertIn('Detailed records', html)
        self.assertNotIn('<table', html)

    def test_wide_word_registration_export_uses_labeled_records_not_cramped_columns(self):
        from docx import Document
        headers = ['Booking reference', 'Camp', 'Registered on', 'Status',
                   'Payment', 'Verification', 'Amount', 'Participants', 'Categories',
                   'Houses', 'Fee review', 'Registration type', 'Tutor approval']
        rows = [['synthetic-ref', 'Synthetic edition', '1 Jan 2038', 'Confirmed',
                 'Paid', 'Verified', '4000', '1', 'Primary', 'House A',
                 'Current', 'paid', '']]
        payload = create_word_report('Registrations report', 'Synthetic edition',
                                     'None', headers, rows)
        document = Document(BytesIO(payload))
        self.assertEqual(len(document.sections), 1)
        # Word's layout is a two-column field/value report, not a thirteen-column table.
        self.assertTrue(document.tables)
        self.assertTrue(all(len(table.columns) <= 2 for table in document.tables))
        text = '\n'.join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
        self.assertIn('Booking reference', text)
        self.assertIn('synthetic-ref', text)
        self.assertIn('Registration type', text)
