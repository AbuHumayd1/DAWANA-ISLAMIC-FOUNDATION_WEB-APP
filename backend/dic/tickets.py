"""Read-only tickets derived from authoritative paid registration records."""
import io
from decimal import Decimal
from django.core import signing
from django.http import HttpResponse
from django.urls import reverse
from rest_framework.exceptions import NotFound, ValidationError
from .models import RegistrationOrderItem, CampEnrollment
from .checkin_services import candidate_for
from .registration_scope import operational_eligibility

SALT = 'dic.registration-ticket.v1'
PREFIX = 'DIC-TICKET:'

def eligible_item(item):
    enrollment = CampEnrollment.objects.filter(
        participant_id=item.participant_id, edition_id=item.order.edition_id).first()
    if enrollment and enrollment.source_item_id != item.pk:
        return False
    result = operational_eligibility(candidate_for(item, enrollment))
    return result['eligible'] and result['code'] == 'verified_paid'

def ticket_token(item):
    return PREFIX + signing.Signer(salt=SALT).sign(str(item.pk))

def resolve_ticket(token, edition):
    if not isinstance(token, str) or len(token) > 160 or not token.startswith(PREFIX):
        raise ValidationError('Invalid registration ticket.')
    try:
        value = signing.Signer(salt=SALT).unsign(token[len(PREFIX):])
        item_id = int(value)
    except (signing.BadSignature, ValueError):
        raise ValidationError('Invalid registration ticket.') from None
    item = RegistrationOrderItem.objects.select_related('order__edition','participant','category').filter(
        pk=item_id, order__edition=edition).first()
    if not item or not eligible_item(item):
        raise ValidationError('This ticket is unavailable for the selected camp edition.')
    return item

def ticket_rows(order):
    items = list(order.items.select_related('order__edition','participant','category').order_by('pk'))
    if not items or not all(eligible_item(item) for item in items):
        raise NotFound('Verified registration tickets are unavailable.')
    revision = order.current_price_revision
    if not revision:
        raise NotFound('Verified pricing is unavailable.')
    prices = {row.order_item_id: row.fee_snapshot_ngn for row in revision.items.all()}
    if set(prices) != {item.pk for item in items} or sum(prices.values(), Decimal(0)) != revision.total_amount_ngn:
        raise NotFound('Verified pricing requires review.')
    return [(item, prices[item.pk]) for item in items]

def ticket_manifest(order, route, **kwargs):
    rows = ticket_rows(order)
    url = reverse(route, kwargs=kwargs)
    join = '&' if '?' in url else '?'
    return {'group_url': url, 'total': str(order.total_amount_ngn),
            'individuals': [{'name': item.participant.full_name, 'fee': str(fee),
                             'url': url + join + 'ticket_item=' + str(item.pk)}
                            for item, fee in rows]}

def ticket_pdf(order, item_id=None):
    import qrcode
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    rows = ticket_rows(order)
    individual = item_id is not None
    if individual:
        rows = [(item, fee) for item, fee in rows if item.pk == item_id]
        if not rows:
            raise NotFound('Ticket unavailable.')
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle('DIC registration ticket and receipt')
    width, height = A4
    green, gold = HexColor('#103E30'), HexColor('#B79B58')
    style = ParagraphStyle('name', fontName='Helvetica-Bold', fontSize=15, leading=19, textColor=green)
    def header():
        pdf.setFillColor(green); pdf.rect(0,height-150,width,150,fill=1,stroke=0)
        pdf.setFillColor(white); pdf.setFont('Helvetica-Bold',13)
        pdf.drawString(38,height-38,'DAWANA ISLAMIC FOUNDATION')
        pdf.setFont('Helvetica-Bold',24); pdf.drawString(38,height-72,'DARUL ISLAM CAMP')
        pdf.setFont('Helvetica',12); pdf.drawString(38,height-99,'INDIVIDUAL TICKET' if individual else 'GROUP TICKET & PAYMENT RECEIPT')
        pdf.drawString(38,height-122, str(order.edition.year))
        pdf.setFillColor(gold); pdf.rect(0,height-154,width,4,fill=1,stroke=0)
        pdf.setFillColor(green); pdf.setFont('Helvetica',10)
        pdf.drawString(38,height-178,'Booking: '+str(order.public_id))
        pdf.drawString(38,height-194,f'{order.edition.camp_start_date:%d %b %Y} - {order.edition.camp_end_date:%d %b %Y}')
        pdf.setFont('Helvetica-Bold',13)
        pdf.drawString(38,height-220, 'Verified payment: NGN '+format(rows[0][1] if individual else order.total_amount_ngn, ',.2f'))
        pdf.setFont('Helvetica',9)
        pdf.drawString(38,32,'Registration ticket only. Arrival is confirmed separately by authorized camp staff.')
    header()
    y = height-254
    for item, fee in rows:
        if y < 175:
            pdf.showPage(); header(); y=height-254
        pdf.setStrokeColor(gold); pdf.roundRect(38,y-112,width-76,110,8,stroke=1,fill=0)
        name=Paragraph(escape(item.participant.full_name),style)
        _, h=name.wrap(width-225,85)
        name.drawOn(pdf,50,y-14-h)
        pdf.setFillColor(green); pdf.setFont('Helvetica',10)
        pdf.drawString(50,y-68,str(item.category_name_snapshot)[:55])
        pdf.drawString(50,y-84,'Fee: NGN '+format(fee,',.2f'))
        pdf.drawString(50,y-99,f'Ticket DIC-{order.edition.year}-{item.pk}')
        image=qrcode.make(ticket_token(item)).convert('RGB')
        pdf.drawImage(ImageReader(image),width-145,y-105,100,100)
        y-=124
    pdf.save()
    response=HttpResponse(buffer.getvalue(),content_type='application/pdf')
    response['Content-Disposition']='attachment; filename="DIC-ticket-'+str(item_id if individual else order.public_id)+'.pdf"'
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response
