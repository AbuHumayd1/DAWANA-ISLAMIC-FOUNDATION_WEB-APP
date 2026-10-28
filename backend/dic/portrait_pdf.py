"""Actual-size portrait badges using existing authorized card contexts."""
import base64
import io
import re
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from rest_framework.exceptions import APIException
from .identity_branding import official_logo_data

mm = 72 / 25.4
A4 = (210 * mm, 297 * mm)


class PDFUnavailable(APIException):
    status_code = 503
    default_detail = 'PDF rendering is unavailable. Ask the administrator to install the declared PDF dependencies.'


def require_pdf_dependencies():
    try:
        import reportlab.pdfgen.canvas
        import qrcode
        import PIL.Image
    except ImportError:
        raise PDFUnavailable() from None


def geometry():
    width, height = getattr(settings, 'DIC_ID_BADGE_SIZE_MM', (90, 130))
    gap = 6
    if (width, height) != (90, 130):
        raise ValueError('The approved DIC portrait badge must be exactly 90 x 130 mm.')
    return width * mm, height * mm, gap * mm


def house_details(enrollment):
    from .identity_cards import housing
    from .models import HouseAllocation
    name = housing(enrollment)
    allocation = HouseAllocation.objects.filter(participant=enrollment.participant,
        edition=enrollment.edition, status='allocated', house__name=name).select_related('house').first()
    colour = allocation.house.badge_colour if allocation else ''
    # None means no approved house colour; neutral presentation is not an assignment.
    return name, colour if re.fullmatch(r'#[0-9a-fA-F]{6}', colour) else None


def image_data(data):
    from reportlab.lib.utils import ImageReader
    return ImageReader(io.BytesIO(base64.b64decode(data.split(',', 1)[1])))


def paragraph(pdf, value, x, top, width, height, size, colour, bold=False):
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    while size >= 5:
        style = ParagraphStyle('badge', fontName='BadgeBold' if bold else 'Badge',
            fontSize=size, leading=size * 1.18, textColor=colour, alignment=1)
        text = Paragraph(escape(value), style)
        _, used = text.wrap(width, height)
        if used <= height:
            text.drawOn(pdf, x, top - used)
            return
        size -= .5
    raise ValueError('Badge text exceeds available space.')


def render_pdf(cards):
    """Render already-authorized contexts with the approved hybrid layout.

    Callers retain eligibility, booking/staff authority, QR resolution and audits.
    House metadata is resolved server-side, never accepted from submitted data.
    """
    require_pdf_dependencies()
    from .premium_hybrid_badge import _render_hybrid_pdf
    resolved = []
    for card in cards:
        name, colour = house_details(card['enrollment'])
        resolved.append({**card, 'house': name, 'house_colour': colour,
            'house_assigned': name not in ('Housing assignment pending',
                                          'Housing awaiting supervisor review')})
    return _render_hybrid_pdf(resolved)
