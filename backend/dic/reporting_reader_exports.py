"""Readable, privacy-minimizing operational Word report from authorized aggregates.

Unlike raw administrative extracts, this document intentionally omits individual
booking references, personal contacts and detail rows. The documented measure
definitions and underlying permission checks remain those of the reporting API.
"""
from io import BytesIO
from decimal import Decimal

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _display(value, unit='count'):
    if value is None:
        return 'Unavailable'
    if unit == 'NGN kobo':
        return '₦{:,.2f}'.format(Decimal(value) / 100)
    if unit == 'percent':
        return '{:,.1f}%'.format(float(value))
    if isinstance(value, (int, float, Decimal)):
        return '{:,}'.format(value)
    return str(value)


def _chart(points, money=False):
    from PIL import Image, ImageDraw, ImageFont
    valid = [(str(p.get('label') or 'Unspecified')[:37], p.get('value'))
             for p in points[:12] if isinstance(p.get('value'), (int, float, Decimal))]
    if not valid:
        return None
    image = Image.new('RGB', (1100, 80 + 62 * len(valid)), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 21)
    except OSError:
        font = ImageFont.load_default()
    peak = max((abs(float(value)) for _, value in valid), default=0) or 1
    for index, (label, value) in enumerate(valid):
        y = 22 + index * 62
        draw.text((15, y), label, fill='#194b34', font=font)
        start, end = 405, 945
        draw.rounded_rectangle((start, y + 6, end, y + 31), radius=9, fill='#e5eee6')
        width = max(2, round(abs(float(value)) / peak * (end-start)))
        draw.rounded_rectangle((start, y + 6, start + width, y + 31),
                               radius=9, fill='#247453')
        draw.text((968, y), _display(value, 'NGN kobo' if money else 'count')[:10], fill='#194b34', font=font)
    output = BytesIO()
    image.save(output, 'PNG')
    output.seek(0)
    return output


def create_reader_report(data):
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(.85)
    section.bottom_margin = Inches(.75)
    section.left_margin = Inches(.9)
    section.right_margin = Inches(.9)

    body = document.styles['Normal']
    body.font.name = 'Aptos'
    body.font.size = Pt(10)
    body.font.color.rgb = RGBColor(36, 63, 47)

    header = section.header.paragraphs[0]
    header.text = 'DAWANA ISLAMIC FOUNDATION  /  CAMP OPERATIONS'
    header.style = document.styles['Caption']
    for run in header.runs:
        run.font.bold = True
        run.font.color.rgb = RGBColor(150, 113, 48)
        run.font.size = Pt(8)

    for style_name in ('Title', 'Heading 1', 'Heading 2'):
        document.styles[style_name].font.name = 'Georgia'
        document.styles[style_name].font.color.rgb = RGBColor(18, 76, 51)
    document.add_heading(data['title'], 0)
    document.add_paragraph(data['edition']['name'])
    document.add_paragraph(
        'Generated: ' + data['generated_at'].replace('T', ' ')[:16] +
        ' WAT  ·  Scope: ' + data.get('scope_label', 'Authorized reporting evidence'))

    document.add_heading('At a glance', level=1)
    metrics = data.get('metrics', [])
    if not metrics:
        document.add_paragraph('No report measures are available for this selection.')
    else:
        # The measured summary remains compact and does not serialize raw records.
        table = document.add_table(rows=0, cols=2)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        for measure in metrics:
            row = table.add_row().cells
            row[0].text = measure['label']
            row[1].text = _display(measure.get('value'), measure.get('unit', 'count'))
            for cell in row:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                color = OxmlElement('w:shd')
                color.set(qn('w:fill'), 'F1F6F1')
                cell._tc.get_or_add_tcPr().append(color)
            for run in row[0].paragraphs[0].runs:
                run.font.color.rgb = RGBColor(76, 101, 82)
                run.font.size = Pt(9)
            for run in row[1].paragraphs[0].runs:
                run.font.color.rgb = RGBColor(18, 76, 51)
                run.font.size = Pt(12)
                run.bold = True

    for title, points in data.get('series', {}).items():
        document.add_heading(title, level=2)
        visual = _chart(points, money='(kobo)' in title)
        if visual:
            document.add_picture(visual, width=Inches(6.5))
        else:
            document.add_paragraph('No numeric breakdown is available for this section.')

    # Supporting technical details are intentionally brief and demoted.
    if data.get('notes'):
        document.add_heading('Interpretation and limitations', level=2)
        for note in data['notes'][:6]:
            document.add_paragraph(note, style='List Bullet')
    document.add_paragraph(
        'This report is based on recorded camp evidence. For individual administrative '
        'records use the separately authorized source-data exports.')

    footer = section.footer.paragraphs[0]
    footer.text = 'DAWANA Islamic Foundation · Authorized operational summary'
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    output = BytesIO()
    document.save(output)
    return output.getvalue()
