"""Atomic creation only; never gives the assisting browser payer capabilities."""
import hmac
import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from dic.models import CampEdition, Participant
from dic.security import digest_value
from dic.views import _create_order, _request_fingerprint, IdempotencyConflict
from .models import RegistrationAssistance


def require_assistance(user):
    if not (user.is_authenticated and user.is_active and user.is_staff
            and user.has_perm('dic.can_view_dic_operations')
            and user.has_perm('dic_assistance.can_assist_registration')):
        raise PermissionDenied('Assisted booking permission is required.')


def receipt(assistance, replayed):
    # No order UUID, contact, payment reference, private status or payer token.
    return {'assistance_id': str(assistance.pk), 'created_at': assistance.created_at.isoformat(),
            'registration_created': True, 'payment_started': False, 'idempotent_replay': replayed,
            'recovery_path': '/dic/register/recover',
            'message': 'Booking saved. The payer must recover it privately using their registered contact on their own device. No payment has been verified.'}


@transaction.atomic
def create_assistance(user, request_id, payload):
    require_assistance(user)
    try:
        request_id = uuid.UUID(str(request_id))
        if request_id.version != 4: raise ValueError()
    except (ValueError, AttributeError):
        raise ValidationError('A random UUIDv4 request_id is required.')
    fingerprint = _request_fingerprint(payload)
    # Lock all editions in stable order, including inactive ones, so replay across
    # an active-edition switch and concurrent public creation remain serialized.
    editions = list(CampEdition.objects.select_for_update().order_by('pk'))
    previous = RegistrationAssistance.objects.filter(request_id=request_id).first()
    if previous:
        if previous.actor_id != user.pk or not hmac.compare_digest(previous.fingerprint, fingerprint):
            raise IdempotencyConflict()
        return receipt(previous, True)
    from dic.recovery import channel_available
    payer = payload.get('primary_registrant', {})
    if not ((payer.get('email') and channel_available('email')) or
            (payer.get('phone') and (channel_available('sms') or channel_available('whatsapp')))):
        raise ValidationError('Payer recovery delivery is unavailable.')
    edition = next((item for item in editions if item.is_active), None)
    if not edition:
        raise ValidationError('No active registration edition.')
    # Conservative review gate: names+DOB are candidates, never identity proof.
    # Do not disclose, edit, resume, merge or take ownership of an existing person.
    people = payload['participants']
    identities = [(p['full_name'].strip().casefold(), p['date_of_birth']) for p in people]
    if len(set(identities)) != len(identities):
        raise ValidationError('Repeated camper details require existing-booking review.')
    for person in people:
        if Participant.objects.filter(full_name__iexact=person['full_name'].strip(),
                date_of_birth=person['date_of_birth'], registration_items__order__edition=edition).exists():
            raise ValidationError('Potential existing registration. Use private payer recovery or authorized identity review; no booking was created.')
    # Namespace keys so a public request cannot replay this internal creation.
    key = digest_value('dic-assistance:' + str(request_id))
    order, unused_token, replayed = _create_order(key_digest=key, fingerprint=fingerprint, payload=payload)
    if replayed or order.edition_id != edition.pk:
        raise IdempotencyConflict()
    # Discard/revoke the initial unshared capability. Recovery issues its own.
    order.access_token_digest = digest_value(str(uuid.uuid4()))
    order.access_token_expires_at = timezone.now()
    order.save(update_fields=('access_token_digest', 'access_token_expires_at'))
    assistance = RegistrationAssistance.objects.create(actor=user, order=order,
        edition=edition, request_id=request_id, fingerprint=fingerprint)
    return receipt(assistance, False)
