"""Staff card rendering and safe, minimal QR verification. No check-in state."""
import base64
import io
import re
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from .models import DigitalIDIssue, HouseAllocation, GuardianRelationship
from .participant_services import eligibility, id_command, record
from .identity_tokens import new_token, read_token, digest


def require_staff(user, manage=False):
    permission = 'dic.can_manage_dic_ids' if manage else 'dic.can_view_dic_ids'
    if not user.is_authenticated or not user.is_active or not user.is_staff or not user.has_perm(permission):
        raise PermissionDenied('Authorized participant identification staff access is required.')


def current_issue(enrollment):
    return enrollment.id_issues.filter(revoked_at__isnull=True).order_by('-version').first()


@transaction.atomic
def command(enrollment, action, actor, reason):
    require_staff(actor, manage=True)
    if action not in ('issue', 'reissue', 'revoke') or len(reason) > 240:
        from rest_framework.exceptions import ValidationError
        raise ValidationError('Choose issue, reissue or revoke; reasons may contain up to 240 characters.')
    issue = id_command(enrollment.pk, action, actor=actor, reason=reason)
    # Existing IDs from migration 0014 receive a QR only on an explicit issuance POST.
    if issue and action in ('issue', 'reissue') and not issue.verification_digest:
        issue.verification_digest, issue.verification_secret = new_token()
        issue.save(update_fields=['verification_digest', 'verification_secret'], issuance_actor=actor)
        record('participant_qr_activated', enrollment, actor, issue=str(issue.pk))
    return issue


def housing(enrollment):
    if enrollment.source_item.order.registration_basis == 'tutor':
        return 'DIC Tutor'
    from .housing_policy import validate_occupant
    from django.core.exceptions import ValidationError
    rows = list(HouseAllocation.objects.filter(edition=enrollment.edition, participant=enrollment.participant,
                                              status='allocated').select_related('house'))
    if len(rows) == 1:
        try:
            if rows[0].house.edition_id != enrollment.edition_id:
                raise ValidationError('Edition mismatch.')
            validate_occupant(enrollment.participant, enrollment.edition, rows[0].house)
            return rows[0].house.name
        except ValidationError:
            return 'Housing awaiting supervisor review'
    return 'Housing assignment pending'


def card_context(request, enrollment):
    from rest_framework.exceptions import ValidationError
    from cryptography.fernet import InvalidToken
    from django.core.exceptions import ImproperlyConfigured
    from botocore.exceptions import BotoCoreError, ClientError
    issue = current_issue(enrollment)
    if not eligibility(enrollment)['eligible'] or not issue or issue.expires_at <= timezone.now():
        raise ValidationError('No active, eligible ID is available. Review eligibility and issue a card first.')
    if not issue.verification_digest:
        raise ValidationError('This legacy ID needs explicit staff QR activation using Issue ID.')
    import qrcode
    from qrcode.image.svg import SvgPathImage
    try:
        token = read_token(issue)
    except InvalidToken:
        raise ValidationError('QR encryption key changed; authorized replacement is required.') from None
    url = request.build_absolute_uri(reverse('dic:verify-id')) + '#' + token
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    qr_image = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    qr_image.save(buffer)
    portrait = None
    portrait_status = 'Photograph not supplied'
    if enrollment.portrait:
        try:
            with enrollment.portrait.open('rb') as image:
                portrait = 'data:image/jpeg;base64,' + base64.b64encode(image.read()).decode('ascii')
        except (FileNotFoundError, OSError, ImproperlyConfigured, BotoCoreError, ClientError):
            portrait = None  # A missing local approved file must not prevent a usable card.
            portrait_status = 'Photograph currently unavailable'
    return dict(enrollment=enrollment, issue=issue, house=housing(enrollment), portrait=portrait, portrait_status=portrait_status,
                qr='data:image/svg+xml;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii'),
                verification_url=url)


def verify(token, actor=None):
    # No numeric participant/issue IDs, query-string tokens or prefix matching.
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    issue = DigitalIDIssue.objects.filter(verification_digest=digest(token), revoked_at__isnull=True,
        expires_at__gt=timezone.now()).select_related('enrollment__participant', 'enrollment__edition').first()
    if not issue or not eligibility(issue.enrollment)['eligible']:
        return None
    enrollment = issue.enrollment
    response = {'status': 'valid', 'edition': enrollment.edition.name}
    staff = bool(actor and actor.is_authenticated and actor.is_active and actor.is_staff and actor.has_perm('dic.can_view_dic_ids'))
    if staff:
        response.update(name=enrollment.participant.full_name, participant_number=enrollment.participant_number,
                        house=housing(enrollment))
    record('participant_qr_verified', enrollment, actor if staff else None, issue=str(issue.pk), staff=staff)
    return response
