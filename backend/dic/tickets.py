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
            'individuals': [{'name': item.participant.full_name, 'fee': str(fee), 'category': item.category_name_snapshot,
                             'reference': f'DIC-{order.edition.year}-{item.pk}',
                             'url': url + join + 'ticket_item=' + str(item.pk)}
                            for item, fee in rows]}

def ticket_pdf(order, item_id=None):
    import base64
    import qrcode
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.pdfbase import pdfmetrics
    from xml.sax.saxutils import escape
    from .identity_branding import official_logo_data
    from .premium_badge_concepts import register_fonts

    rows = ticket_rows(order)
    if item_id is not None:
        rows = [(item, fee) for item, fee in rows if item.pk == item_id]
        if not rows:
            raise NotFound('Ticket unavailable.')
    single = len(rows) == 1
    receipt = item_id is None or order.items.count() == 1
    register_fonts()
    green, gold, ivory, muted, white = '#103E30', '#B79B58', '#FFFDF4', '#476356', '#FFFFFF'
    width, height = (648, 324) if single else A4
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width,height))
    pdf.setTitle('DIC admission ticket and receipt' if receipt else 'DIC admission ticket')
    logo = official_logo_data()
    theme = str((order.edition.general_information or {}).get('theme') or '')
    title = 'DIC '+str(order.edition.year)
    dates = f'{order.edition.camp_start_date:%d %b %Y} – {order.edition.camp_end_date:%d %b %Y}'

    def box(x,y,w,h,fill,stroke=None,r=0):
        pdf.setFillColor(HexColor(fill)); pdf.setStrokeColor(HexColor(stroke or fill))
        if r:
            pdf.roundRect(x,y,w,h,r,fill=1,stroke=bool(stroke))
        else:
            pdf.rect(x,y,w,h,fill=1,stroke=bool(stroke))

    def text(value,x,top,w,h,size=11,font='PremiumSans',colour=green,minimum=7):
        value = str(value)
        while size >= minimum:
            style=ParagraphStyle('ticket',fontName=font,fontSize=size,leading=size*1.15,textColor=HexColor(colour),splitLongWords=True)
            paragraph=Paragraph(escape(value),style)
            _,used=paragraph.wrap(w,h)
            if used <= h:
                paragraph.drawOn(pdf,x,top-used)
                return
            size-=.5
        raise ValidationError('Ticket text exceeds the printable layout. Contact DIC support.')

    def money(amount):
        font = pdfmetrics.getFont('PremiumBold')
        prefix = '₦' if 8358 in font.face.charToGlyph else 'NGN '
        return prefix+format(amount,',.2f')

    def brand(x,top,w):
        offset=0
        if logo:
            box(x,top-36,36,36,white,r=5)
            pdf.drawImage(ImageReader(io.BytesIO(base64.b64decode(logo.split(',',1)[1]))),x+3,top-33,30,30,preserveAspectRatio=True,anchor='c',mask='auto')
            offset=46
        text('DAWANA ISLAMIC FOUNDATION',x+offset,top-1,w-offset,14,10,'PremiumBold',white)
        text('DARUL ISLAM CAMP',x+offset,top-17,w-offset,16,12,'PremiumBold',white)

    def qr(item,x,y,side):
        image=qrcode.make(ticket_token(item)).convert('RGB')
        pdf.drawImage(ImageReader(image),x,y,side,side)

    if single:
        item,fee=rows[0]
        box(0,0,width,height,ivory)
        box(0,height-101,width,101,green)
        box(0,height-104,width,3,gold)
        brand(24,height-17,390)
        text(title,24,height-61,340,30,24,'PremiumSerif',white)
        text(theme.upper(),350,height-27,270,25,15,'PremiumBold',white)
        text('ADMISSION TICKET & RECEIPT' if receipt else 'INDIVIDUAL ADMISSION TICKET',350,height-61,270,24,10,'PremiumBold',white)
        text('CAMPER',24,208,370,12,8,'PremiumBold',muted)
        text(item.participant.full_name,24,192,390,42,22,'PremiumBold',green,11)
        text(item.category_name_snapshot,24,145,390,18,12)
        text(dates,24,124,390,16,10,'PremiumBold')
        text(order.edition.venue_name,24,107,390,28,10)
        box(24,47,390,27,'#E5EDE4',r=5)
        text('PAYMENT VERIFIED  |  '+money(fee),34,66,370,16,11,'PremiumBold')
        text('Ticket '+f'DIC-{order.edition.year}-{item.pk}',24,39,390,12,9,'PremiumBold')
        text('Booking: '+str(order.public_id),24,24,390,14,8)
        box(435,16,197,193,white,'#D9D1B9',8)
        text('SCAN AT ARRIVAL',449,196,169,17,10,'PremiumBold')
        qr(item,468,47,130)
        text('Staff verification required',449,37,169,16,9)
    else:
        def header():
            box(0,0,width,height,ivory)
            box(0,height-138,width,138,green)
            box(0,height-141,width,3,gold)
            brand(32,height-21,width-64)
            text(title+'  /  '+theme.upper(),32,height-65,width-64,28,22,'PremiumSerif',white)
            text('GROUP TICKET & PAYMENT RECEIPT',32,height-103,width-64,20,12,'PremiumBold',white)
            text(dates,32,height-157,width-64,16,11,'PremiumBold')
            text(order.edition.venue_name,32,height-176,width-64,26,11)
            text('Booking: '+str(order.public_id),32,height-204,width-64,16,9)
            box(32,height-265,width-64,40,'#E5EDE4',r=6)
            text('PAYMENT VERIFIED  |  '+str(len(rows))+' campers  |  '+money(order.total_amount_ngn),44,height-236,width-88,25,13,'PremiumBold')
            text('Present each camper QR at arrival. Staff confirmation is required.',32,30,width-64,14,9)
        header()
        y=height-280
        for item,fee in rows:
            if y-116 < 45:
                pdf.showPage(); header(); y=height-280
            box(32,y-112,width-64,112,white,'#D9D1B9',8)
            text(item.participant.full_name,46,y-13,width-204,36,16,'PremiumBold',green,10)
            text(item.category_name_snapshot,46,y-53,width-204,18,10)
            text(money(fee),46,y-72,width-204,16,12,'PremiumBold')
            text(f'DIC-{order.edition.year}-{item.pk}',46,y-92,width-204,13,9)
            qr(item,width-144,y-105,96)
            y-=124
    pdf.save()
    response=HttpResponse(buffer.getvalue(),content_type='application/pdf')
    response['Content-Disposition']='attachment; filename="DIC-ticket-'+str(rows[0][0].pk if single else order.public_id)+'.pdf"'
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response
