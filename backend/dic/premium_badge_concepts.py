"""Two review-only ReportLab concepts. No route or production renderer uses these.

Accepts synthetic contexts only, with explicit house/house_colour fixture values.
No models, issuance, verification, payment, database or audit operations.
"""
import io
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape
from .portrait_pdf import geometry, mm, A4, image_data, require_pdf_dependencies
from .identity_branding import official_logo_data

CONCEPTS = {
    'classic-executive': dict(label='Classic Executive', qr=(47, 36, 34), accent_x=8, accent_sample_x=9),
    'modern-premium': dict(label='Modern Premium', qr=(49, 37, 33), accent_x=6, accent_sample_x=7),
}
GREEN = '#174a34'
DEEP = '#103b2c'
GOLD = '#b49654'
CREAM = '#fffdf4'
NEUTRAL = '#e7ebe5'
# Badge-local mm, measured down from the top. Includes 0.5 mm text safety insets.
NAME_BOX = (7, 76, 76, 28)
NAME_MINIMUM_PT = 11


def register_fonts():
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from django.conf import settings
    fallback = Path(reportlab.__file__).parent / 'fonts'
    candidates = {
        # Liberation provides Arial-compatible Linux advances. DejaVu/Vera are
        # wider and can turn the approved 16 pt single line into two lines.
        'PremiumSans': [getattr(settings, 'DIC_ID_FONT_FILE', ''), 'C:/Windows/Fonts/arial.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', fallback/'Vera.ttf'],
        'PremiumBold': [getattr(settings, 'DIC_ID_BOLD_FONT_FILE', ''), 'C:/Windows/Fonts/arialbd.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', fallback/'VeraBd.ttf'],
        'PremiumSerif': ['C:/Windows/Fonts/georgiab.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', fallback/'VeraBd.ttf'],
    }
    for name, paths in candidates.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            chosen = next((Path(p) for p in paths if p and Path(p).is_file()), None)
            if chosen is None:
                raise ValueError('An approved readable font is required for premium previews.')
            pdfmetrics.registerFont(TTFont(name, str(chosen)))


class BadgePainter:
    """Millimetre, top-origin drawing helpers; physical badge is never scaled."""
    def __init__(self, pdf):
        from reportlab.lib.colors import HexColor
        self.pdf, self.colour = pdf, HexColor

    def box(self, x, top, width, height, fill, stroke=None, radius=0, line=.18):
        pdf = self.pdf
        pdf.setFillColor(self.colour(fill))
        pdf.setStrokeColor(self.colour(stroke or fill))
        pdf.setLineWidth(line*mm)
        args = (x*mm, (130-top-height)*mm, width*mm, height*mm)
        if radius:
            pdf.roundRect(*args, radius*mm, fill=1, stroke=bool(stroke))
        else:
            pdf.rect(*args, fill=1, stroke=bool(stroke))

    def text(self, value, x, top, width, max_height, size=10, minimum=8,
             font='PremiumSans', colour=GREEN, align=1):
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        original_size = size
        while size >= minimum:
            style = ParagraphStyle('premium', fontName=font, fontSize=size,
                leading=size*1.12, textColor=self.colour(colour), alignment=align,
                splitLongWords=True, spaceShrinkage=0)
            text = Paragraph(escape(str(value)), style)
            _, height = text.wrap(width*mm, max_height*mm)
            if height <= max_height*mm+.01:
                text.drawOn(self.pdf, x*mm, (130-top)*mm-height)
                return height/mm
            size -= .25
        # Never clip, truncate or shrink participant names below the readability floor.
        raise ValueError(f'Text does not fit the {original_size:g} pt design at its readable minimum; review this name/layout.')

    def star(self, x, top, radius=5):
        pdf = self.pdf
        path = pdf.beginPath()
        for index in range(16):
            angle = index*math.pi/8
            r = radius if index%2 == 0 else radius*.48
            px, py = (x+math.cos(angle)*r)*mm, (130-top+math.sin(angle)*r)*mm
            (path.moveTo if index == 0 else path.lineTo)(px, py)
        path.close()
        pdf.setStrokeColor(self.colour(GOLD))
        pdf.setLineWidth(.12*mm)
        pdf.drawPath(path, stroke=1, fill=0)

    def logo(self, logo, classic):
        if classic:
            self.pdf.setFillColor(self.colour(CREAM))
            self.pdf.setStrokeColor(self.colour(GOLD))
            self.pdf.setLineWidth(.2*mm)
            self.pdf.circle(45*mm, (130-14)*mm, 9.5*mm, stroke=1, fill=1)
            self.pdf.drawImage(image_data(logo), 37.5*mm, (130-21.5)*mm,
                15*mm, 15*mm, preserveAspectRatio=True, anchor='c', mask='auto')
        else:
            self.box(8, 8, 20, 20, CREAM, GOLD, radius=3)
            self.pdf.drawImage(image_data(logo), 10*mm, (130-26)*mm,
                16*mm, 16*mm, preserveAspectRatio=True, anchor='c', mask='auto')

    def portrait(self, card, x, top, width, height, classic):
        self.box(x, top, width, height, '#f0f0e6', GOLD if classic else GREEN, radius=2, line=.25)
        if card['portrait']:
            # Contain the original raster without stretching or removing face content.
            self.pdf.drawImage(image_data(card['portrait']), (x+1)*mm, (130-top-height+1)*mm,
                (width-2)*mm, (height-2)*mm, preserveAspectRatio=True, anchor='c', mask='auto')
        else:
            self.pdf.setFillColor(self.colour('#b5c2b5'))
            self.pdf.circle((x+width/2)*mm, (130-top-height*.32)*mm, width*.14*mm, fill=1, stroke=0)
            self.box(x+width*.24, top+height*.51, width*.52, height*.22, '#b5c2b5', radius=3)
            self.text(card.get('portrait_status', 'Photograph pending'), x+2, top+height-6,
                width-4, 5, size=6.5, minimum=6.5)

    def qr(self, card, concept):
        import qrcode
        from reportlab.lib.utils import ImageReader
        x, top, size = CONCEPTS[concept]['qr']
        # Trim only surplus panel padding; the QR and quiet zone are unchanged.
        self.box(x-2, top-2, size+4, size+7, '#ffffff', '#d5d9ca', radius=2, line=.15)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
        qr.add_data(card['verification_url'])
        qr.make(fit=True)
        buffer = io.BytesIO()
        qr.make_image().save(buffer, format='PNG')
        self.pdf.drawImage(ImageReader(io.BytesIO(buffer.getvalue())), x*mm, (130-top-size)*mm, size*mm, size*mm)
        self.text('SCAN TO VERIFY', x-1, top+size+2, size+2, 3, size=6, minimum=6, font='PremiumBold')


def render_concept_pdf(cards, concept):
    if concept not in CONCEPTS:
        raise ValueError('Choose one of the two review concepts.')
    if not cards or any(card.get('synthetic') is not True for card in cards):
        raise ValueError('Premium concepts are synthetic review previews only; production selection is pending.')
    require_pdf_dependencies()
    from reportlab.pdfgen import canvas
    register_fonts()
    logo = official_logo_data()
    if not logo:
        raise ValueError('The original official logo is required; no replacement logo will be invented.')
    width, height, gap = geometry()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    pdf.setTitle('DIC 2026 - '+CONCEPTS[concept]['label']+' - SYNTHETIC CONCEPT')
    classic = concept == 'classic-executive'
    for index, card in enumerate(cards):
        if index and index%4 == 0:
            pdf.showPage()
        pdf.saveState()
        x = (A4[0]-2*width-gap)/2 + index%2*(width+gap)
        y = A4[1]-(A4[1]-2*height-gap)/2-height-(index%4//2)*(height+gap)
        pdf.translate(x, y)
        p = BadgePainter(pdf)
        p.box(0, 0, 90, 130, GREEN)
        p.box(3, 3, 84, 124, CREAM)
        # Inner keyline stays within the full, continuous 3 mm green edge.
        pdf.setStrokeColor(p.colour(GOLD))
        pdf.setLineWidth(.16*mm)
        pdf.rect(3.7*mm, 3.7*mm, 82.6*mm, 122.6*mm, stroke=1, fill=0)
        if classic:
            p.box(4, 4, 82, 29, DEEP)
            p.star(15, 15, 5)
            p.star(75, 15, 5)
            p.logo(logo, True)
            p.text('DAWANA ISLAMIC FOUNDATION', 7, 24, 76, 4, size=9.5, minimum=9.5, colour=CREAM, font='PremiumBold')
            p.text(card['enrollment'].edition.name, 8, 29, 74, 4, size=8.5, minimum=8.5, colour='#ddc58b')
            p.box(8, 33.5, 74, .3, GOLD)
            p.portrait(card, 9, 36, 31, 37, True)
        else:
            p.box(4, 4, 82, 27, DEEP)
            # Restrained diagonal gold detail; it never touches the QR zone.
            path = pdf.beginPath()
            path.moveTo(70*mm, 126*mm)
            path.lineTo(86*mm, 126*mm)
            path.lineTo(86*mm, 116*mm)
            path.close()
            pdf.setFillColor(p.colour('#275740'))
            pdf.drawPath(path, stroke=0, fill=1)
            p.logo(logo, False)
            p.text('DAWANA ISLAMIC FOUNDATION', 32, 9, 49, 9, size=11, minimum=11, colour=CREAM, font='PremiumBold', align=0)
            p.text(card['enrollment'].edition.name, 32, 23, 49, 5, size=8.3, minimum=8.3, colour='#ddc58b', align=0)
            p.box(8, 32, 15, .7, GOLD)
            p.portrait(card, 8, 35, 34, 39, False)
        p.qr(card, concept)
        name_x, name_top, name_width, name_max_height = NAME_BOX
        name_height = p.text(card['enrollment'].participant.full_name,
            name_x+.5, name_top+.5, name_width-1, name_max_height-1,
            size=18 if classic else 19, minimum=NAME_MINIMUM_PT,
            font='PremiumSerif' if classic else 'PremiumBold', align=1 if classic else 0)+1
        number_label_top = name_top+name_height+1
        p.text('PARTICIPANT NUMBER', 8, number_label_top, 74, 3, size=6.5, minimum=6.5, align=1 if classic else 0)
        number_top = number_label_top+3
        p.text(card['enrollment'].participant_number, 8, number_top, 74, 5, size=10.5, minimum=9, font='PremiumBold', align=1 if classic else 0)
        house_top = max(100, number_top+6)
        house_height = min(14 if classic else 22, 124-house_top)
        if house_height < 9:
            raise ValueError('Name and ID leave insufficient readable house space; review this exceptional name.')
        raw = card.get('house_colour')
        accent = raw if isinstance(raw, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', raw) else None
        fill = accent or NEUTRAL
        if classic:
            p.box(8, house_top, 74, house_height, fill, radius=1.5)
            p.box(12, house_top+1, 66, house_height-2, CREAM, radius=.7)
            p.text('HOUSE' if card.get('house_assigned') else 'HOUSING STATUS', 14, house_top+2, 62, 2.7, size=6.3, minimum=6.3)
            p.text(card['house'], 14, house_top+5, 62, house_height-6, size=11, minimum=9.5, font='PremiumSerif')
        else:
            p.box(6, house_top, 78, house_height, fill, radius=2)
            # A light inset guarantees readable lettering even for white/yellow house colours.
            p.box(11, house_top+1.4, 71, house_height-2.8, CREAM, radius=1)
            p.text('HOUSE' if card.get('house_assigned') else 'HOUSING STATUS', 14, house_top+2, 65, 2.7, size=6.3, minimum=6.3, align=0)
            p.text(card['house'], 14, house_top+4.8, 65, house_height-6, size=12, minimum=9.5, font='PremiumBold', align=0)
        p.text('SYNTHETIC CONCEPT - NOT A VALID ID', 8, 125, 74, 1.8, size=4.5, minimum=4.5, colour=GREEN)
        pdf.setStrokeColor(p.colour('#777777'))
        pdf.setLineWidth(.25)
        for cx, cy in [(0, 0), (width, 0), (0, height), (width, height)]:
            dx, dy = (-1 if cx == 0 else 1), (-1 if cy == 0 else 1)
            pdf.line(cx+dx*mm, cy, cx+dx*2.5*mm, cy)
            pdf.line(cx, cy+dy*mm, cx, cy+dy*2.5*mm)
        pdf.restoreState()
    pdf.save()
    return output.getvalue()
