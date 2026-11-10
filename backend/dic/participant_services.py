"""Booking identity and IDs only. No payment mutation or physical-presence state."""
import hashlib
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import CampEnrollment, DigitalIDIssue, DICAdminAuditEvent, RegistrationOrder, RegistrationOrderItem, PaymentAttempt


def source_fingerprint(items):
    return hashlib.sha256(",".join(str(item.pk) for item in sorted(items, key=lambda row: row.pk)).encode()).hexdigest()


def require_id_manager(actor):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.can_manage_dic_ids')):
        raise PermissionDenied('Authorized active ID management staff access is required.')


def eligibility(enrollment):
    item = RegistrationOrderItem.objects.select_related("order", "category").get(pk=enrollment.source_item_id)
    items = list(RegistrationOrderItem.objects.filter(participant_id=enrollment.participant_id, order__edition_id=enrollment.edition_id).select_related("order"))
    if item.participant_id != enrollment.participant_id or item.order.edition_id != enrollment.edition_id or item.category.edition_id != enrollment.edition_id:
        return {"eligible": False, "code": "invalid_source"}
    if len(items) > 1 and enrollment.source_review_fingerprint != source_fingerprint(items):
        return {"eligible": False, "code": "source_review_required"}
    if enrollment.restriction_reason:
        return {"eligible": False, "code": "restricted_review_required"}
    order = RegistrationOrder.objects.select_related("current_price_revision").get(pk=item.order_id)
    if order.status == RegistrationOrder.Status.CANCELLED:
        return {'eligible': False, 'code': 'registration_cancelled'}
    if order.registration_basis == 'tutor':
        from .tutor_registration import tutor_entitlement
        valid = (order.status == 'confirmed' and order.payment_status == 'not_required'
            and order.current_price_revision_id is None and order.total_amount_ngn == 0
            and order.items.count() == 1
            and not order.payment_attempts.exists() and getattr(enrollment, 'pk', None)
            and tutor_entitlement(enrollment, item))
        return {'eligible': bool(valid), 'code': 'authorized_tutor' if valid else 'tutor_authorization_required'}
    if order.status != RegistrationOrder.Status.CONFIRMED or order.payment_status != RegistrationOrder.PaymentStatus.PAID:
        return {"eligible": False, "code": "registration_not_verified_paid"}
    mode = getattr(settings, 'PAYSTACK_MODE', None)
    if mode not in ('test', 'live') or (
        getattr(settings, 'SETTINGS_MODULE', '') in ('config.settings.production', 'config.settings.render', 'config.settings.zevcloud') and mode != 'live'
    ):
        return {"eligible": False, "code": "settlement_evidence_review_required"}
    # SUCCESSFUL is written only by the trusted settlement service. Missing legacy
    # provider evidence is a review case, never a fabricated successful charge.
    # PaymentAttempt is Paystack-only: payment_views verifies its provider response
    # independently (reference, transaction identity, amount, currency and domain).
    # Stored mode must ALSO match on every entitlement read, including old sessions.
    expected = int(order.total_amount_ngn * Decimal(100))
    revision = order.current_price_revision
    if not revision or revision.order_id != order.pk or not revision.accepted_at:
        return {"eligible": False, "code": "settlement_evidence_review_required"}
    attempts = PaymentAttempt.objects.filter(
        order=order, status=PaymentAttempt.Status.SUCCESSFUL, provider_mode=mode, amount_kobo=expected,
        currency="NGN", provider_status="success", provider_reported_amount_kobo=expected,
        provider_reported_currency="NGN", provider_paid_at__isnull=False,
        verified_at__isnull=False, price_revision=revision,
    ).exclude(provider_transaction_id__isnull=True).exclude(provider_transaction_id="")
    from .payment_views import _revision_is_valid_at_payment
    settled = any(_revision_is_valid_at_payment(revision, attempt.provider_paid_at) for attempt in attempts)
    if not settled:
        return {"eligible": False, "code": "settlement_evidence_review_required"}
    if PaymentAttempt.objects.filter(order=order, status__in=("amount_mismatch", "reconcile")).exists():
        return {"eligible": False, "code": "reconciliation_review_required"}
    return {"eligible": True, "code": "verified_paid"}


def record(action, enrollment=None, actor=None, **details):
    DICAdminAuditEvent.objects.create(actor=actor, action=action, target_type="CampEnrollment" if enrollment else "ParticipantPortal", target_id=str(enrollment.pk) if enrollment else "", details=details)


@transaction.atomic
def ensure_enrollment(item_id):
    item = RegistrationOrderItem.objects.select_related("order", "category").get(pk=item_id)
    if item.category.edition_id != item.order.edition_id:
        raise ValidationError("Registration category and edition require staff review.")
    # All issuance/source resolution uses the same participant lock. Enrollment
    # is lazily materialized by a POST, never by a read-only eligibility lookup.
    from .models import Participant
    Participant.objects.select_for_update().get(pk=item.participant_id)
    existing = CampEnrollment.objects.filter(participant=item.participant, edition=item.order.edition).first()
    if existing:
        return existing
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    for attempt in range(5):
        number = f"DIC-{item.order.edition.year}-" + "".join(secrets.choice(alphabet) for _ in range(10))
        try:
            with transaction.atomic():
                enrollment = CampEnrollment.objects.create(participant=item.participant, edition=item.order.edition, source_item=item, participant_number=number)
            break
        except IntegrityError:
            if attempt == 4:
                raise
    record("participant_enrollment_created", enrollment)
    return enrollment


@transaction.atomic
def id_command(enrollment_id, action, actor=None, reason=""):
    if action not in ('issue', 'reissue', 'revoke'):
        raise ValidationError('Unknown participant ID operation.')
    require_id_manager(actor)
    enrollment = CampEnrollment.objects.select_related("source_item__order", "edition").get(pk=enrollment_id)
    # Compatible with order-before-attempt locks in settlement. Lock all sources
    # so a concurrent refund cannot be missed during issuance.
    order_ids = list(RegistrationOrderItem.objects.filter(participant=enrollment.participant, order__edition=enrollment.edition).values_list("order_id", flat=True).distinct())
    list(RegistrationOrder.objects.select_for_update().filter(pk__in=order_ids).order_by("pk"))
    from .models import Participant
    Participant.objects.select_for_update().get(pk=enrollment.participant_id)
    latest_ids = set(RegistrationOrderItem.objects.filter(participant=enrollment.participant, order__edition=enrollment.edition).values_list("order_id", flat=True))
    if latest_ids != set(order_ids):
        raise ValidationError("Registration sources changed. Refresh and retry after review.")
    enrollment = CampEnrollment.objects.select_for_update().select_related("source_item__order", "edition").get(pk=enrollment_id)
    current = enrollment.id_issues.filter(revoked_at__isnull=True).first()
    if action == "revoke":
        if not reason:
            raise ValidationError({"reason": "A reason is required."})
        if current:
            current.revoked_at = timezone.now()
            current.revoked_by = actor
            current.save(update_fields=("revoked_at", "revoked_by"), issuance_actor=actor)
            record("participant_id_revoked", enrollment, actor, issue=str(current.pk), reason=reason)
        return current
    result = eligibility(enrollment)
    if not result["eligible"]:
        raise ValidationError({"detail": result["code"]})
    if action == "issue" and current and current.expires_at > timezone.now():
        return current
    if action == "issue" and enrollment.id_issues.exists():
        raise ValidationError({"detail": "A staff-authorized replacement is required."})
    if action == "reissue" and not reason:
        raise ValidationError({"reason": "A replacement reason is required."})
    if current:
        current.revoked_at = timezone.now()
        current.revoked_by = actor
        current.save(update_fields=("revoked_at", "revoked_by"), issuance_actor=actor)
    version = (enrollment.id_issues.order_by("-version").values_list("version", flat=True).first() or 0) + 1
    expires = timezone.make_aware(datetime.combine(enrollment.edition.camp_end_date + timedelta(days=1), time.min))
    if expires <= timezone.now():
        raise ValidationError({"detail": "This edition's ID validity period has ended."})
    credential = {}
    if actor is not None:
        # Explicit authorized staff issuance shares the same credential path in
        # Operations and Admin. Portal preparation never activates a QR.
        from .identity_tokens import new_token
        credential['verification_digest'], credential['verification_secret'] = new_token()
    issue = DigitalIDIssue(enrollment=enrollment, version=version, expires_at=expires, issued_by=actor, reason=reason, **credential)
    issue.save(issuance_actor=actor)
    record("participant_id_issued", enrollment, actor, issue=str(issue.pk), version=version, reason=reason)
    if credential:
        record('participant_qr_activated', enrollment, actor, issue=str(issue.pk))
    return issue


def id_summary(enrollment):
    current = enrollment.id_issues.order_by("-version").first()
    status = "not_issued" if current is None else "revoked" if current.revoked_at else "expired" if current.expires_at <= timezone.now() else "current"
    result = eligibility(enrollment)
    return {"id": str(enrollment.pk), "participant_number": enrollment.participant_number, "name": enrollment.participant.full_name,
            "registration_basis": enrollment.source_item.order.registration_basis,
            "category": enrollment.source_item.category_name_snapshot, "eligibility": result,
            "issue": {"version": current.version, "status": status, "expires_at": current.expires_at.isoformat()} if current else None}
