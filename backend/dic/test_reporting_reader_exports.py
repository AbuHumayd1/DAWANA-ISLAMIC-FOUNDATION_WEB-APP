"""Reader report uses aggregate metrics and charts, never individual raw records."""
from io import BytesIO
from django.test import SimpleTestCase
from docx import Document
from dic.reporting_reader_exports import create_reader_report


class PremiumIndividualWordReportTests(SimpleTestCase):
    def test_summary_word_preserves_measures_but_not_sensitive_detail_records(self):
        data={
            'title':'Registration and demographics',
            'edition':{'name':'Synthetic Camp 2038'},
            'generated_at':'2038-12-31T12:00:00+01:00',
            'scope_label':'Active registrations',
            'metrics':[{'label':'Registered participants','value':20,'unit':'count'},
                       {'label':'Confirmed booking rate','value':75,'unit':'percent'},
                       {'label':'Gross verified income','value':256000,'unit':'NGN kobo'},
                       {'label':'Missing evidence','value':None,'unit':'count'}],
            'series':{'Registration categories':[
                {'label':'Primary','value':10},
                {'label':'Graduate','value':5}]},
            'rows':[{'booking_reference':'SECRET-BOOKING-REFERENCE',
                     'participant_name':'Private Student','phone':'0123456789'}],
            'notes':['Recorded camp data only.'],
        }
        binary=create_reader_report(data)
        document=Document(BytesIO(binary))
        text=' '.join([p.text for p in document.paragraphs]+[
            cell.text for table in document.tables for row in table.rows for cell in row.cells])
        self.assertIn('Registration and demographics',text)
        self.assertIn('Registered participants',text)
        self.assertIn('20',text)
        self.assertIn('75.0%',text)
        self.assertIn('₦2,560.00',text)
        self.assertIn('Unavailable',text)
        self.assertTrue(document.inline_shapes)
        self.assertNotIn('SECRET-BOOKING-REFERENCE',text)
        self.assertNotIn('Private Student',text)
        self.assertNotIn('0123456789',text)
        self.assertLessEqual(len(document.tables),1)

    def test_no_metric_data_or_chart_values_does_not_invent_zero(self):
        binary=create_reader_report({
            'title':'Feedback and evaluations',
            'edition':{'name':'Synthetic Camp'}, 'generated_at':'2038-12-31T12:00:00+01:00',
            'metrics':[], 'series':{'Suppressed':[
                {'label':'Anonymous sample','value':None}]},'rows':[],'notes':[]})
        document=Document(BytesIO(binary))
        text=' '.join(p.text for p in document.paragraphs)
        self.assertIn('No report measures are available',text)
        self.assertIn('No numeric breakdown is available',text)
