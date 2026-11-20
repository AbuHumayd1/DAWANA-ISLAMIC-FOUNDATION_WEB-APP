"""One-click cross-domain camp evidence brief.

No private rows or personally identifiable information are exported. Every
section is sourced from the same permission-scoped reporting projections used
by Operations, never from made-up denominators or guessed attendance.
"""
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from . import reporting_services as reports

SECTIONS = OrderedDict((
    ('registration', 'Participation and demographics'),
    ('finance', 'Financial performance'),
    ('accommodation', 'Accommodation and housing'),
    ('attendance', 'Arrivals and movement'),
    ('feedback', 'Participant and staff evaluations'),
    ('welfare', 'Welfare and safeguarding'),
    ('academic', 'Verified teaching and learning outcomes'),
))

CHARTS = {
    'registration': ('Registration categories', 'Gender distribution', 'Age at camp start'),
    'finance': ('Gross collections by accepted price category (kobo)',),
    'accommodation': ('Allocated categories', 'Housing queue'),
    'attendance': ('Daily recorded arrivals',),
    'feedback': ('Responses by channel, version and camp day',),
    'welfare': ('Case status', 'Complaint categories'),
}
MAX_POINTS = 20

# The consolidated camp report is an evidence-of-results document, not a
# checkout pipeline dashboard. Operational diagnostics remain in Payments.
COMPREHENSIVE_FINANCE_EXCLUDED_METRICS = frozenset({
    'Expected booking value',
    'Pending attempts',
    'Failed attempts',
    'Exceptional attempts',
    'Recorded adjustment events in period',
    'Gross / accepted-price discrepancy',
})


def display(value, unit='count'):
    if value is None:
        return 'Unavailable'
    if unit == 'NGN kobo':
        return '₦{:,.2f}'.format(Decimal(value) / 100)
    if unit == 'percent':
        return '{:,.1f}%'.format(float(value))
    if isinstance(value, (float, int, Decimal)):
        return '{:,}'.format(value)
    return str(value)


def permit_domain(actor, domain, for_download=False):
    try:
        reports.require_report(actor, domain)
    except PermissionDenied:
        return False
    if for_download and domain == 'finance':
        return all(actor.has_perm('dic_finance.can_' + perm + '_finance')
                   for perm in ('export', 'view_details'))
    return True



def summarize(domain, metrics):
    """Exact, contextual prose built only from the named recorded metrics."""
    values = {m['label']: m['display'] for m in metrics}
    def have(*names):
        return all(name in values for name in names)
    if domain == 'registration' and have('Registered participants', 'Bookings',
                                        'Regular campers', 'Tutor participants',
                                        'Confirmed bookings'):
        return ('The edition recorded ' + values['Registered participants'] +
                ' distinct registered participants across ' + values['Bookings'] +
                ' active bookings. The participant population included ' +
                values['Regular campers'] + ' regular campers and ' +
                values['Tutor participants'] + ' tutor participants. ' +
                values['Confirmed bookings'] + ' bookings were confirmed.')
    if domain == 'finance' and have('Gross verified collections', 'Net verified collections',
                                   'Applied recorded adjustments'):
        return ('Verified payment evidence shows ' + values['Gross verified collections'] +
                ' in gross collections and ' + values['Applied recorded adjustments'] +
                ' in applied recorded adjustments, resulting in ' +
                values['Net verified collections'] +
                ' in net verified collections. These amounts are not proof of bank settlement.')
    if domain == 'accommodation' and have('Assigned campers in allocation window',
                                          'Current occupancy in selected houses'):
        return ('Housing records show ' + values['Assigned campers in allocation window'] +
                ' distinct campers allocated in the reporting window. Current recorded ' +
                'house occupancy is ' + values['Current occupancy in selected houses'] +
                '. Allocation does not independently prove physical attendance.')
    if domain == 'attendance' and have('Recorded arrivals in window',
                                       'Recorded departures in window', 'Recorded returns in window'):
        return ('The movement system recorded ' + values['Recorded arrivals in window'] +
                ' arrival check-ins, ' + values['Recorded departures in window'] +
                ' departures and ' + values['Recorded returns in window'] +
                ' returns. Unrecorded arrivals cannot be classified as confirmed absences.')
    if domain == 'feedback' and have('Visible reporting groups'):
        return (values['Visible reporting groups'] +
                ' feedback reporting groups are available at the configured privacy threshold. ' +
                'Anonymous responses cannot be attributed to individuals.')
    if domain == 'welfare' and have('Complaints', 'Outstanding cases'):
        return ('The system recorded ' + values['Complaints'] +
                ' welfare cases, with ' + values['Outstanding cases'] +
                ' currently outstanding. Case identities and confidential narratives are excluded.')
    known = [m for m in metrics if m['value'] is not None]
    return ('The available evidence includes ' +
            '; '.join(m['label'].lower() + ': ' + m['display'] for m in known[:3]) +
            '.' if known else 'No quantified measures are currently available.')

def build(edition, actor, *, for_download=False):
    # Check the baseline capability before accessing any edition evidence.
    reports.require_report(actor, 'overview')
    selected = reports.filters({}, 'registration')
    sections = []
    for domain, name in SECTIONS.items():
        if not permit_domain(actor, domain, for_download):
            sections.append({'domain': domain, 'title': name, 'state': 'restricted',
                             'metrics': [], 'charts': [], 'notes': [],
                             'summary': 'This section is omitted because the current account lacks the required permission.'})
            continue
        source = reports.report(edition, selected, actor, domain)
        if not source.get('available'):
            sections.append({'domain': domain, 'title': name, 'state': 'unavailable',
                             'metrics': [], 'charts': [], 'notes': source.get('notes', []),
                             'summary': 'This source has not been configured or does not provide sufficient recorded evidence.'})
            continue
        metrics = [{'label': m['label'], 'value': m.get('value'),
                    'unit': m.get('unit', 'count'),
                    'display': display(m.get('value'), m.get('unit', 'count'))}
                   for m in source.get('metrics', [])]
        if domain == 'finance':
            metrics = [m for m in metrics if m['label'] not in COMPREHENSIVE_FINANCE_EXCLUDED_METRICS]
        charts = []
        for chart_name in CHARTS.get(domain, ()):
            points = source.get('series', {}).get(chart_name, [])
            if not points:
                continue
            points = points[:MAX_POINTS]
            scale = max((abs(float(p.get('value') or 0)) for p in points), default=0) or 1
            charts.append({'title': chart_name,
                           'points': [{'label': str(p.get('label', 'Unknown'))[:90],
                                       'width': round(abs(float(p.get('value') or 0)) * 100 / scale, 1),
                                       'value': p.get('value'),
                                       'display': display(p.get('value'),
                                           'NGN kobo' if '(kobo)' in chart_name else 'count')}
                                      for p in points]})
        # Contextual language is deterministic and anchored to named measures.
        summary = summarize(domain, metrics)
        sections.append({'domain': domain, 'title': name, 'state': 'recorded',
                         'metrics': metrics, 'charts': charts,
                         'notes': source.get('notes', [])[:5], 'summary': summary})
    from .aftercamp_evidence import additional_sections, approved_assessments
    sections.extend(additional_sections(edition, actor, for_download=for_download))
    committee_assessments = approved_assessments(edition)
    generated = timezone.localtime(timezone.now(), reports.TZ)
    end_date = edition.camp_end_date
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    executive_highlights = [
        {'title': section['title'], 'finding': section['summary']}
        for section in sections if section['state']=='recorded'
        and any(metric.get('value') is not None for metric in section.get('metrics', []))
    ][:6]
    evidence_gaps = [
        {'title': section['title'], 'reason': section['summary']}
        for section in sections if section['state'] != 'recorded'
    ]
    from .aftercamp_models import ASSESSMENT_TOPICS
    assessment_ready = len(committee_assessments) == len(ASSESSMENT_TOPICS)
    return {
        'executive_highlights': executive_highlights,
        'evidence_gaps': evidence_gaps,
        'committee_approval_complete': assessment_ready,
        'committee_approvals_required': len(ASSESSMENT_TOPICS),
        'edition': {'id': edition.pk, 'name': edition.name,
                    'start_date': str(edition.camp_start_date),
                    'end_date': str(end_date)},
        'generated_at': generated.isoformat(),
        'generated_display': generated.strftime('%d %B %Y, %H:%M WAT'),
        'timezone': 'Africa/Lagos',
        'report_status': 'Post-camp snapshot' if generated.date() > end_date else 'Interim snapshot — camp not yet completed',
        'sections': sections,
        'committee_assessments': committee_assessments,
        'assessment_coverage': len(committee_assessments),
        'covered_count': sum(s['state'] == 'recorded' for s in sections),
        'total_sections': len(sections),
        'methodology': [
            'All figures are computed from persisted camp records at the generation time. Missing evidence is never counted as zero.',
            'A camp registration, a verified payment and a recorded arrival are separate facts with different denominators.',
            'Financial figures are verified payment evidence, not independently confirmed bank settlement.',
            'Teaching, food service, activities and scoring require their own validated operational measures before the report may be described as a complete camp assessment.',
            'Restricted domains are omitted rather than bypassing permissions. Anonymous feedback and confidential welfare case details are not disclosed.',
        ],
    }


def _bar_chart(points, title):
    """Rasterize a simple clean chart into memory; no external dependencies."""
    from PIL import Image, ImageDraw, ImageFont
    points = [(str(p['label'])[:36], float(p.get('value') or 0), p.get('display', ''))
              for p in points if p.get('value') is not None and
              isinstance(p.get('value'), (int, float, Decimal))]
    if not points:
        return None
    points = points[:10]
    width = 1000
    height = 100 + 62 * len(points)
    img = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        font = ImageFont.truetype(font_path, 20)
    except OSError:
        font = ImageFont.load_default()
    max_value = max(abs(v) for _, v, _ in points) or 1
    for i, (label, value, formatted) in enumerate(points):
        y = 30 + i * 62
        draw.text((16, y), label, font=font, fill='#1c4935')
        left, right = 350, 905
        draw.rounded_rectangle((left, y + 4, right, y + 28), radius=8, fill='#e4eee5')
        draw.rounded_rectangle((left, y + 4, left + max(2, int(abs(value) * (right - left) / max_value)), y + 28),
                               radius=8, fill='#217249')
        draw.text((920, y), str(formatted)[:14], font=font, fill='#1c4935')
    stream = BytesIO()
    img.save(stream, format='PNG')
    stream.seek(0)
    return stream


def export_word(payload):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    document = Document()
    sec = document.sections[0]
    sec.top_margin = Inches(.75)
    sec.bottom_margin = Inches(.7)
    sec.left_margin = Inches(.83)
    sec.right_margin = Inches(.83)
    normal = document.styles['Normal']
    normal.font.name = 'Aptos'
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor(36, 58, 45)
    title = document.add_heading('DIC CAMP REPORT', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(payload['edition']['name']).alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(payload['report_status'] + ' · ' + payload['generated_display'])
    document.add_heading('Executive overview', 1)
    document.add_paragraph(
        'This document consolidates authorized operational measurements for the camp edition. '
        'It distinguishes recorded results from missing data, preserving denominators and confidentiality.')
    document.add_paragraph(
        str(payload['covered_count']) + ' of ' + str(payload['total_sections']) +
        ' reporting domains presently have recorded measures available to this account.')
    for highlight in payload.get('executive_highlights', []):
        document.add_heading(highlight['title'], 2)
        document.add_paragraph(highlight['finding'])
    if payload.get('evidence_gaps'):
        document.add_heading('Evidence requiring follow-up', 2)
        for gap in payload['evidence_gaps']:
            document.add_paragraph(gap['title'] + ': ' + gap['reason'], style='List Bullet')
    if not payload.get('committee_approval_complete', False):
        document.add_paragraph(
            'Committee assessment incomplete: this document is an evidence-backed '
            'snapshot and is not yet the final approved camp performance assessment.')
    for section in payload['sections']:
        document.add_heading(section['title'], 1)
        if section['state'] != 'recorded':
            document.add_paragraph(section['summary'])
            for note in section['notes'][:2]:
                document.add_paragraph(note, style='List Bullet')
            continue
        document.add_paragraph(section['summary'])
        core = section['metrics'][:12]
        if core:
            table = document.add_table(rows=0, cols=2)
            table.style = 'Light Shading Accent 1'
            for m in core:
                cells = table.add_row().cells
                cells[0].text = m['label']
                cells[1].text = m['display']
        for chart in section['charts'][:3]:
            document.add_heading(chart['title'], 2)
            visual = _bar_chart(chart['points'], chart['title'])
            if visual is not None:
                document.add_picture(visual, width=Inches(6.5))
            else:
                document.add_paragraph('No numeric data available for this chart.')
        if section['notes']:
            document.add_paragraph('Interpretation: ' + section['notes'][0])
    document.add_heading('Approved committee assessment', 1)
    assessments = payload.get('committee_assessments', [])
    if not assessments:
        document.add_paragraph('No committee assessment has yet been approved for this edition.')
    for assessment in assessments:
        document.add_heading(assessment['title'], 2)
        for label, field in (('Findings','findings'),('Challenges','challenges'),
                             ('Recommendations','recommendations')):
            if assessment.get(field):
                document.add_heading(label, 3)
                document.add_paragraph(assessment[field])
        if assessment.get('evidence_reference'):
            document.add_paragraph('Evidence: ' + assessment['evidence_reference'])
    document.add_heading('Reporting limitations and next steps', 1)
    for note in payload['methodology']:
        document.add_paragraph(note, style='List Bullet')
    document.add_paragraph('Prepared from recorded DAWANA operational evidence; not an independently audited financial statement.')
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.text = 'DAWANA Islamic Foundation · Authorized camp reporting'
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
