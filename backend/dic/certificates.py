"""Artwork-backed personalization; no substitute artwork or invented signatures."""
import hashlib
import io
from pathlib import Path
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from .models import CertificateRelease, ParticipationCertificate, DICAdminAuditEvent, CampCheckIn


def approved_artwork(config):
    config.full_clean()
    root=Path(__file__).parent/'assets/certificates'
    candidate=root/config.artwork
    path=str(candidate) if candidate.is_file() else None
    if not path or not config.artwork_sha256 or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=config.artwork_sha256:
        raise ValidationError('Approved designer artwork is missing or its reviewed checksum does not match.')
    return path


def release_for(edition):
    config=CertificateRelease.objects.filter(edition=edition).first()
    if not config or not config.enabled or not config.release_at or timezone.now()<config.release_at:
        raise PermissionDenied('Certificates have not been released.')
    approved_artwork(config)
    return config


def confirmed_camp_arrival(item):
    """Participation requires an actual recorded arrival, not a booking attempt.

    The camper portal's existing scope check separately enforces that this
    participant belongs to the authenticated user.
    """
    return CampCheckIn.objects.filter(
        edition_id=item.order.edition_id,
        participant_id=item.participant_id,
    ).exists()


@transaction.atomic
def issue(item):
    # Serialize issuance through the existing participant identity lock.
    from .models import Participant
    Participant.objects.select_for_update().get(pk=item.participant_id)
    if not confirmed_camp_arrival(item):
        raise PermissionDenied('A confirmed camp check-in is required for this certificate.')
    release_for(item.order.edition)
    record,created=ParticipationCertificate.objects.get_or_create(edition=item.order.edition,
        participant=item.participant,defaults={'participant_name':item.participant.full_name})
    if record.revoked_at: raise PermissionDenied('This certificate has been revoked. Contact authorized staff.')
    if created:
        DICAdminAuditEvent.objects.create(action='certificate_issued',target_type='ParticipationCertificate',
            target_id=str(record.reference),details={'participant':str(item.participant_id),'edition':item.order.edition_id})
    return record


def fitted_lines(text,font,width,height):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words=text.split()
    for size in range(36,15,-1):
        lines=['']
        for word in words:
            if stringWidth(word,font,size)>width: break
            next_line=(lines[-1]+' '+word).strip()
            if stringWidth(next_line,font,size)>width: lines.append(word)
            else: lines[-1]=next_line
        else:
            if len(lines)*size*1.25<=height: return size,lines
    raise ValidationError('The approved name box cannot fit this name legibly; enlarge its placement before release.')


def render_certificate(record,config):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    # Bundled Vera font retains accented names; standard Helvetica is not a Unicode substitute.
    import reportlab
    font_path=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
    if not font_path.is_file(): raise ValidationError('Certificate Unicode font is not installed.')
    if 'DawanaCertificate' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DawanaCertificate',str(font_path)))
    path=approved_artwork(config)
    image=ImageReader(path);iw,ih=image.getSize()
    if abs(iw/ih-config.page_width/config.page_height)>.025:
        raise ValidationError('Approved artwork aspect ratio does not match the certificate page.')
    output=io.BytesIO();pdf=canvas.Canvas(output,pagesize=(config.page_width,config.page_height))
    pdf.setTitle('Certificate of Participation - '+str(record.reference))
    pdf.setSubject(str(record.edition)+' | '+str(record.edition.camp_start_date)+' to '+str(record.edition.camp_end_date))
    pdf.setAuthor('DAWANA Islamic Foundation')
    pdf.drawImage(image,0,0,width=config.page_width,height=config.page_height)
    for text,box in [(record.participant_name,config.name_box),(str(record.reference),config.reference_box)]:
        if not box: continue
        font=pdfmetrics.getFont('DawanaCertificate')
        if any(ord(char) not in font.face.charToGlyph for char in text if not char.isspace()):
            raise ValidationError('The approved certificate font needs glyphs for this participant name; no characters were substituted.')
        x,y,width,height=box
        size,lines=fitted_lines(text,'DawanaCertificate',width,height)
        pdf.setFont('DawanaCertificate',size);pdf.setFillColorRGB(.035,.24,.16)
        top=y+(height+len(lines)*size*1.25)/2-size
        for index,line in enumerate(lines): pdf.drawCentredString(x+width/2,top-index*size*1.25,line)
    pdf.showPage();pdf.save();return output.getvalue()
