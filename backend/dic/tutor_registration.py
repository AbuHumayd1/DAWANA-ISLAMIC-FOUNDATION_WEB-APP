"""Narrow complimentary tutor entitlement; no payment settlement mutations."""
from datetime import timedelta
import hashlib
import json
import secrets
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import (TutorRegistrationAuthorization, TutorVerification, CampEdition,
    Participant, PrimaryRegistrant, RegistrationOrder, RegistrationOrderItem,
    RegistrationCategory, DICAdminAuditEvent, ParticipantPortalScope)
from .security import digest_value
from .recovery import normalize_email


def can_authorize_tutors(actor):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.can_authorize_dic_tutors')):
        return False
    # Django superusers otherwise inherit every new permission automatically.
    # This entitlement requires an actual designated user/group grant as well.
    if getattr(actor, 'is_superuser', False):
        return (actor.user_permissions.filter(content_type__app_label='dic', codename='can_authorize_dic_tutors').exists()
            or actor.groups.filter(permissions__content_type__app_label='dic', permissions__codename='can_authorize_dic_tutors').exists())
    return True


def require_authorizer(actor):
    if not can_authorize_tutors(actor):
        raise PermissionDenied('Explicit tutor authorization permission is required.')


def audit(auth, actor, action, **details):
    DICAdminAuditEvent.objects.create(actor=actor, action='tutor_' + action,
        target_type='TutorRegistrationAuthorization', target_id=str(auth.pk), details=details)


def is_tutor(participant_id, edition_id):
    # Includes revoked tutors: revocation must never move them into camper housing.
    return RegistrationOrderItem.objects.filter(participant_id=participant_id,
        order__edition_id=edition_id, order__registration_basis='tutor').exists()


def authorization_state(order):
    if order.registration_basis != 'tutor':
        return None
    from .models import CampEnrollment
    from .participant_services import eligibility
    enrollment = CampEnrollment.objects.filter(source_item__order=order).first()
    return eligibility(enrollment)['code'] if enrollment else 'tutor_authorization_required'


def valid_invitation(auth, now=None):
    now = now or timezone.now()
    return bool(auth and auth.invitation_digest and not auth.revoked_at and not auth.redeemed_at
        and auth.expires_at and now < auth.expires_at and auth.edition.tutor_registration_enabled
        and auth.edition.is_active and auth.edition.camp_end_date >= timezone.localdate())


def tutor_entitlement(enrollment, item):
    return TutorRegistrationAuthorization.objects.filter(enrollment_id=enrollment.pk,
        enrollment__participant_id=enrollment.participant_id, enrollment__source_item_id=item.pk,
        edition_id=enrollment.edition_id, redeemed_at__isnull=False, verified_at__isnull=False,
        revoked_at__isnull=True, email__iexact=item.participant.email,
        intended_name__iexact=item.participant.full_name).exists()


@transaction.atomic
def authorize(actor, edition, intended_name, email, reason):
    require_authorizer(actor)
    if not reason.strip() or not intended_name.strip():
        raise ValidationError('Tutor name and authorization reason are required.')
    # Shared edition lock also serializes public/assisted registration duplicate checks.
    CampEdition.objects.select_for_update().get(pk=edition.pk)
    auth = TutorRegistrationAuthorization.objects.create(edition=edition,
        intended_name=intended_name.strip(), email=normalize_email(email), reason=reason.strip(),
        authorized_by=actor, authorized_at=timezone.now())
    audit(auth, actor, 'authorized', reason=reason.strip())
    return auth


@transaction.atomic
def issue(actor, authorization_id, reason):
    require_authorizer(actor)
    auth = TutorRegistrationAuthorization.objects.select_for_update(of=('self',)).select_related('edition').get(pk=authorization_id)
    if not reason.strip() or auth.redeemed_at or auth.revoked_at:
        raise ValidationError('Only unused, unrevoked authorizations can be issued; a reason is required.')
    if not auth.edition.tutor_registration_enabled or not auth.edition.is_active or auth.edition.camp_end_date < timezone.localdate():
        raise ValidationError('Tutor registration is unavailable for this edition.')
    previous = auth.invitation_digest
    token = secrets.token_urlsafe(32)
    auth.invitation_digest = digest_value(token)
    auth.issued_at = timezone.now()
    auth.expires_at = auth.issued_at + timedelta(days=7)
    auth.save(update_fields=['invitation_digest', 'issued_at', 'expires_at'])
    TutorVerification.objects.filter(authorization=auth).update(capability_digest='', code_digest='')
    audit(auth, actor, 'reissued' if previous else 'issued', reason=reason.strip(),
          previous_digest=previous, expires_at=auth.expires_at.isoformat())
    return token


@transaction.atomic
def revoke(actor, authorization_id, reason):
    require_authorizer(actor)
    # Match existing order -> participant -> enrollment -> authorization lock order.
    reference = TutorRegistrationAuthorization.objects.select_related('enrollment__source_item').get(pk=authorization_id)
    if reference.enrollment_id:
        RegistrationOrder.objects.select_for_update().get(pk=reference.enrollment.source_item.order_id)
        Participant.objects.select_for_update().get(pk=reference.enrollment.participant_id)
        from .models import CampEnrollment
        CampEnrollment.objects.select_for_update().get(pk=reference.enrollment_id)
    auth = TutorRegistrationAuthorization.objects.select_for_update().get(pk=authorization_id)
    if not reason.strip():
        raise ValidationError('A revocation reason is required.')
    if auth.revoked_at:
        return
    # An unused authorization may have been redeemed while acquiring locks: retry safely.
    if auth.enrollment_id != reference.enrollment_id:
        raise ValidationError('Registration changed; refresh and retry revocation.')
    auth.revoked_at, auth.revoked_by, auth.revocation_reason = timezone.now(), actor, reason.strip()
    auth.save(update_fields=['revoked_at', 'revoked_by', 'revocation_reason'])
    TutorVerification.objects.filter(authorization=auth).update(capability_digest='', code_digest='')
    if auth.enrollment_id:
        # Authorization does not grant ID management. Eligibility immediately disables all
        # credentials, and direct revocation below records the responsible authorizer.
        auth.enrollment.id_issues.filter(revoked_at__isnull=True).update(revoked_at=auth.revoked_at, revoked_by=actor)
        order_id = auth.enrollment.source_item.order_id
        ParticipantPortalScope.objects.filter(order_id=order_id).update(revoked_at=auth.revoked_at)
        RegistrationOrder.objects.filter(pk=order_id).update(access_token_revoked_at=auth.revoked_at)
    audit(auth, actor, 'revoked', reason=reason.strip())


def validate_tutor(data, auth):
    from .registration_age import validate_declaration, exact_age
    from django.core.exceptions import ValidationError as ModelError
    try:
        validate_declaration(data['age_declaration'], data['date_of_birth'], timezone.localdate())
        if data['date_of_birth'] is not None and exact_age(data['date_of_birth'], timezone.localdate()) < 18:
            raise ModelError('Tutors must be adults.')
    except ModelError as error:
        raise ValidationError(error.messages)
    if data['age_declaration'] == 'minor' or normalize_email(data['email']) != auth.email:
        raise ValidationError('Adult registration with the authorized email is required.')
    if ' '.join(data['full_name'].casefold().split()) != ' '.join(auth.intended_name.casefold().split()):
        raise ValidationError('Tutor identity differs from the authorized identity; contact your administrator.')


@transaction.atomic
@sensitive_variables()
def redeem(verification_id, browser, capability, data, credentials=None):
    reference = TutorVerification.objects.select_related('authorization').get(pk=verification_id)
    CampEdition.objects.select_for_update().get(pk=reference.authorization.edition_id)
    auth = TutorRegistrationAuthorization.objects.select_for_update(of=('self',)).select_related('edition').get(pk=reference.authorization_id)
    verification = TutorVerification.objects.select_for_update().get(pk=verification_id)
    now = timezone.now()
    if not (verification.verified_at and verification.expires_at > now
            and verification.invitation_digest == auth.invitation_digest and not auth.revoked_at
            and secrets.compare_digest(verification.browser_digest, digest_value(browser))
            and verification.capability_digest and secrets.compare_digest(verification.capability_digest, digest_value(capability))):
        raise ValidationError('Tutor verification is unavailable. Request a new invitation verification.')
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    if auth.redeemed_at:
        if verification.request_fingerprint != fingerprint:
            raise ValidationError('This invitation was already used with different details.')
        order = auth.enrollment.source_item.order
        if credentials:
            from .registration_accounts import bind_registration
            bind_registration(order, credentials)
        return order
    if not valid_invitation(auth, now):
        raise ValidationError('Tutor invitation is unavailable.')
    validate_tutor(data, auth)
    if Participant.objects.filter(registration_items__order__edition=auth.edition).filter(
            models_duplicate(data)).exists():
        raise ValidationError('Possible existing registration; authorized identity review is required.')
    category, _ = RegistrationCategory.objects.get_or_create(edition=auth.edition,
        name='DIC Tutor', defaults=dict(is_active=False, fee_ngn=0))
    if category.is_active or category.fee_ngn != 0:
        raise ValidationError('Internal tutor category requires administrator review.')
    person = dict(data)
    person['full_name'], person['email'] = auth.intended_name, auth.email
    person.pop('category_id', None)
    if person['date_of_birth'] is None:
        person['adult_declared_on'] = timezone.localdate()
    participant = Participant.objects.create(**person)
    registrant = PrimaryRegistrant.objects.create(full_name=participant.full_name, email=auth.email, phone=participant.phone)
    order = RegistrationOrder.objects.create(edition=auth.edition, primary_registrant=registrant,
        registration_basis='tutor', status='confirmed', payment_status='not_required',
        idempotency_key_digest=digest_value('tutor:' + str(auth.pk)), request_fingerprint=fingerprint,
        access_token_digest=digest_value(secrets.token_urlsafe(32)))
    item = RegistrationOrderItem.objects.create(order=order, participant=participant, category=category, fee_snapshot_ngn=0)
    from .participant_services import ensure_enrollment
    auth.enrollment = ensure_enrollment(item.pk)
    auth.redeemed_at, auth.verified_at = now, verification.verified_at
    auth.save(update_fields=['enrollment', 'redeemed_at', 'verified_at'])
    verification.request_fingerprint = fingerprint
    verification.save(update_fields=['request_fingerprint'])
    if credentials:
        from .registration_accounts import bind_registration
        bind_registration(order, credentials)
    audit(auth, None, 'redeemed', enrollment=str(auth.enrollment_id), order=str(order.public_id))
    return order


def models_duplicate(data):
    from django.db.models import Q
    return Q(email__iexact=data['email']) | Q(full_name__iexact=data['full_name'], date_of_birth=data['date_of_birth'])
