"""Purpose-isolated booking OTPs and cookies; never Django staff authentication."""
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError, AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (CampEnrollment, ParticipantPortalChallenge, ParticipantPortalGrant, ParticipantPortalScope,
                     RegistrationOrder, RegistrationOrderItem, HouseAllocation, Participant)
from .operations_api import OperationsBaseView, _can, _paginate
from .participant_services import ensure_enrollment, eligibility, id_command, id_summary, record, source_fingerprint
from .recovery import available_channels, channel_available, encrypt_delivery_payload, normalize_email, normalize_phone
from .recovery_views import (_consume_request_limits, _normalize_contact, _challenge_code, _code_digest,
                             _contact_digest, CODE_TTL, MAX_CODE_ATTEMPTS, RecoveryChannelUnavailable)
from .security import digest_value

COOKIE = "dawana_participant"
BROWSER_COOKIE = "dawana_participant_challenge"
COOKIE_PATH = "/api/v1/dic/participant/"
GENERIC = "If the booking reference and registered primary contact match, a code will be sent. Do not share it."
INVALID = "The code could not be verified. Check the details or request a new code."


def primary_contact_matches(order, channel, contact_hash):
    raw = order.primary_registrant.email if channel == "email" else order.primary_registrant.phone
    try:
        normalized = normalize_email(raw) if channel == "email" else normalize_phone(raw)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(_contact_digest(channel, normalized), contact_hash)


def cookie(response, name, value, seconds):
    response.set_cookie(name, value, max_age=seconds, httponly=True,
                        secure=settings.SESSION_COOKIE_SECURE, samesite="Lax", path=COOKIE_PATH)


@ensure_csrf_cookie
@require_GET
def portal_csrf(request):
    response = JsonResponse({"csrfToken": get_token(request)})
    response["Cache-Control"] = "no-store"
    return response


class PortalView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "dic_participant_session"

    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def authorized_grant(request, lock=False):
    token = request.COOKIES.get(COOKIE, "")
    if not token or len(token) > 256:
        raise AuthenticationFailed("Your participant session has expired. Please verify again.")
    query = ParticipantPortalGrant.objects.select_for_update() if lock else ParticipantPortalGrant.objects
    grant = query.filter(credential_digest=digest_value(token), revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not grant:
        raise AuthenticationFailed("Your participant session has expired. Please verify again.")
    return grant


def scoped_orders(grant):
    orders = RegistrationOrder.objects.filter(
        participantportalscope__grant=grant, participantportalscope__revoked_at__isnull=True,
        access_token_revoked_at__isnull=True,
    ).exclude(status="cancelled").select_related("edition", "primary_registrant")
    return [order for order in orders if primary_contact_matches(order, grant.channel, grant.contact_digest)]


def scoped_enrollment(request, enrollment_id):
    grant = authorized_grant(request)
    orders = scoped_orders(grant)
    enrollment = CampEnrollment.objects.filter(pk=enrollment_id, source_item__order_id__in=[o.pk for o in orders]).select_related("participant", "source_item__order", "edition").first()
    if not enrollment:
        raise NotFound("Participant record not found.")
    return grant, enrollment


class PortalOptionsView(PortalView):
    def get(self, request):
        return Response({"channels": [{"value": c.key, "label": c.label, "available": c.available} for c in available_channels()]})


class PortalChallengeView(PortalView):
    throttle_scope = "dic_participant_request"

    def post(self, request):
        channel = request.data.get("channel")
        contact = _normalize_contact(channel, request.data.get("contact"))
        if len(contact) > 254:
            raise ValidationError("Contact is too long.")
        if not channel_available(channel):
            raise RecoveryChannelUnavailable()
        try:
            reference = uuid.UUID(str(request.data.get("order_reference", "")))
        except ValueError as exc:
            raise ValidationError({"order_reference": "Enter the full booking reference."}) from exc
        now = timezone.now()
        contact_hash = _consume_request_limits(channel, contact, request, now)
        order = RegistrationOrder.objects.filter(public_id=reference, access_token_revoked_at__isnull=True).exclude(status="cancelled").select_related("primary_registrant").first()
        if order and not primary_contact_matches(order, channel, contact_hash):
            order = None
        browser = secrets.token_urlsafe(32)
        code = _challenge_code()
        with transaction.atomic():
            old = request.COOKIES.get(BROWSER_COOKIE, "")
            if old:
                ParticipantPortalChallenge.objects.filter(browser_digest=digest_value(old), consumed_at__isnull=True).update(consumed_at=now, encrypted_delivery_payload="")
            challenge = ParticipantPortalChallenge.objects.create(
                order=order, channel=channel, contact_digest=contact_hash, browser_digest=digest_value(browser),
                code_digest="", expires_at=now + CODE_TTL,
                encrypted_delivery_payload=encrypt_delivery_payload(channel, contact, code),
            )
            challenge.code_digest = _code_digest(challenge.pk, code)
            challenge.save(update_fields=("code_digest",))
            record("participant_otp_requested", challenge_id=str(challenge.pk))
        response = Response({"detail": GENERIC, "challenge_id": str(challenge.pk), "expires_in": int(CODE_TTL.total_seconds()), "resend_after": 60}, status=202)
        cookie(response, BROWSER_COOKIE, browser, int(CODE_TTL.total_seconds()))
        return response


class PortalVerifyView(PortalView):
    throttle_scope = "dic_participant_verify"

    def post(self, request):
        try:
            challenge_id = uuid.UUID(str(request.data.get("challenge_id", "")))
        except ValueError as exc:
            raise ValidationError(INVALID) from exc
        code = request.data.get("code", "")
        if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
            raise ValidationError(INVALID)
        failed = True
        with transaction.atomic():
            challenge = ParticipantPortalChallenge.objects.select_for_update().filter(pk=challenge_id).first()
            now = timezone.now()
            browser = request.COOKIES.get(BROWSER_COOKIE, "")
            if challenge and not challenge.consumed_at and challenge.expires_at > now and challenge.attempts < MAX_CODE_ATTEMPTS and hmac.compare_digest(challenge.browser_digest, digest_value(browser)):
                challenge.attempts += 1
                valid = challenge.delivery_status == "sent" and hmac.compare_digest(challenge.code_digest, _code_digest(challenge.pk, code))
                order = RegistrationOrder.objects.select_related("primary_registrant").filter(pk=challenge.order_id, access_token_revoked_at__isnull=True).exclude(status="cancelled").first()
                valid = valid and order is not None and primary_contact_matches(order, challenge.channel, challenge.contact_digest)
                if valid or challenge.attempts >= MAX_CODE_ATTEMPTS:
                    challenge.consumed_at = now
                    challenge.encrypted_delivery_payload = ""
                challenge.save(update_fields=("attempts", "consumed_at", "encrypted_delivery_payload"))
                if valid:
                    ParticipantPortalGrant.objects.filter(credential_digest=digest_value(request.COOKIES.get(COOKIE, "")), revoked_at__isnull=True).update(revoked_at=now)
                    token = secrets.token_urlsafe(32)
                    grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value(token), channel=challenge.channel, contact_digest=challenge.contact_digest, expires_at=now + timedelta(minutes=30))
                    ParticipantPortalScope.objects.create(grant=grant, order=order)
                    record("participant_portal_authenticated", grant_id=str(grant.pk))
                    failed = False
            if failed:
                record("participant_otp_rejected")
        # Failed-attempt counters commit, rather than roll back on exceptions.
        if failed:
            raise ValidationError(INVALID)
        response = Response({"authenticated": True, "expires_at": grant.expires_at.isoformat()})
        cookie(response, COOKIE, token, 1800)
        response.delete_cookie(BROWSER_COOKIE, path=COOKIE_PATH, samesite="Lax")
        return response


class PortalMeView(PortalView):
    def get(self, request):
        grant = authorized_grant(request)
        return Response({"authenticated": True, "expires_at": grant.expires_at.isoformat(), "booking_count": len(scoped_orders(grant))})


class PortalLogoutView(PortalView):
    def post(self, request):
        with transaction.atomic():
            grant = authorized_grant(request, lock=True)
            grant.revoked_at = timezone.now()
            grant.save(update_fields=("revoked_at",))
            record("participant_portal_logout", grant_id=str(grant.pk))
        response = Response(status=204)
        response.delete_cookie(COOKIE, path=COOKIE_PATH, samesite="Lax")
        response.delete_cookie(BROWSER_COOKIE, path=COOKIE_PATH, samesite="Lax")
        return response


class PortalEnrollmentsView(PortalView):
    def get(self, request):
        grant = authorized_grant(request)
        results = []
        for order in scoped_orders(grant):
            participants = []
            for item in order.items.select_related("participant"):
                enrollment = CampEnrollment.objects.filter(participant=item.participant, edition=order.edition, source_item__order=order).select_related("participant", "source_item__order", "edition").first()
                summary = id_summary(enrollment) if enrollment else {"name": item.participant.full_name, "category": item.category_name_snapshot, "id": None, "participant_number": None, "issue": None}
                if not enrollment:
                    # Unsaved candidate keeps reads side-effect free.
                    candidate = CampEnrollment(participant=item.participant, edition=order.edition, source_item=item)
                    summary["eligibility"] = eligibility(candidate)
                summary["registration_item_id"] = item.pk
                participants.append(summary)
            results.append({"reference": str(order.public_id), "edition": order.edition.name, "payment_status": order.payment_status, "status": order.status, "participants": participants})
        record("participant_bookings_viewed", grant_id=str(grant.pk),
               order_count=len(results), participant_count=sum(len(row["participants"]) for row in results))
        return Response({"orders": results})

    def post(self, request):
        grant = authorized_grant(request)
        item_id = request.data.get("registration_item_id")
        if not isinstance(item_id, int):
            raise ValidationError("Choose a participant.")
        item = RegistrationOrderItem.objects.filter(pk=item_id, order_id__in=[o.pk for o in scoped_orders(grant)]).first()
        if not item:
            raise NotFound("Participant record not found.")
        enrollment = ensure_enrollment(item.pk)
        if enrollment.source_item.order_id != item.order_id:
            raise ValidationError("Registration source requires staff review.")
        id_command(enrollment.pk, "issue")
        record("participant_id_accessed", enrollment, grant_id=str(grant.pk))
        return Response(id_summary(enrollment))


def card_data(enrollment):
    summary = id_summary(enrollment)
    if not summary["eligibility"]["eligible"] or not summary["issue"] or summary["issue"]["status"] != "current":
        raise ValidationError("No currently eligible ID is available. Contact authorized staff for review.")
    edition = enrollment.edition
    allocations = HouseAllocation.objects.filter(participant=enrollment.participant, edition=edition, house__edition=edition, house__status="active", status="allocated").select_related("house")
    house = allocations.first() if allocations.count() == 1 else None
    return {"name": summary["name"], "participant_number": summary["participant_number"], "category": summary["category"],
            "edition": edition.name, "starts": edition.camp_start_date, "ends": edition.camp_end_date, "venue": edition.venue_name,
            "house": house.house.name if house else None, "version": summary["issue"]["version"],
            "logo_url": settings.DIC_OFFICIAL_LOGO_URL or None, "branding_verified": bool(settings.DIC_OFFICIAL_LOGO_URL)}


class PortalIDView(PortalView):
    def get(self, request, enrollment_id):
        grant, enrollment = scoped_enrollment(request, enrollment_id)
        data = card_data(enrollment)
        record("participant_id_viewed", enrollment, grant_id=str(grant.pk))
        return Response(data)


class StaffEnrollmentView(OperationsBaseView):
    def get(self, request):
        if not _can(request.user, "can_view_dic_ids"):
            raise PermissionDenied()
        query = CampEnrollment.objects.select_related("participant", "source_item__order", "edition").order_by("participant_number")
        number = request.query_params.get("q", "").strip()
        if number:
            from django.db.models import Q
            query = query.filter(Q(participant_number__iexact=number) | Q(participant__full_name__icontains=number) | Q(source_item__order__public_id__icontains=number))
        def summary(enrollment):
            data = id_summary(enrollment)
            if _can(request.user, "can_review_dic_enrollment_sources"):
                data["restriction_reason"] = enrollment.restriction_reason
                data["sources"] = [{"id": i.pk, "reference": str(i.order.public_id), "status": i.order.status, "payment_status": i.order.payment_status} for i in RegistrationOrderItem.objects.filter(participant=enrollment.participant, order__edition=enrollment.edition).select_related("order")]
            return data
        data = _paginate(query, request, summary)
        candidates = RegistrationOrderItem.objects.select_related("participant", "order__edition").order_by("-pk")
        if number:
            candidates = candidates.filter(Q(participant__full_name__icontains=number) | Q(order__public_id__icontains=number))
        data["registration_candidates"] = [{"registration_item_id": i.pk, "name": i.participant.full_name, "edition": i.order.edition.name, "category": i.category_name_snapshot} for i in candidates[:25]]
        record("staff_participant_ids_searched", actor=request.user, page=data["page"],
               result_count=len(data["results"]), candidate_count=len(data["registration_candidates"]),
               searched=bool(number))
        return Response(data)

    def post(self, request):
        if not _can(request.user, "can_manage_dic_ids"):
            raise PermissionDenied()
        item_id = request.data.get("registration_item_id")
        if not isinstance(item_id, int) or not RegistrationOrderItem.objects.filter(pk=item_id).exists():
            raise ValidationError("Choose a valid registration item.")
        enrollment = ensure_enrollment(item_id)
        record("staff_enrollment_accessed", enrollment, request.user)
        return Response(id_summary(enrollment))


class StaffIDView(OperationsBaseView):
    def get(self, request, enrollment_id):
        if not _can(request.user, "can_view_dic_ids"):
            raise PermissionDenied()
        enrollment = CampEnrollment.objects.filter(pk=enrollment_id).select_related("participant", "source_item__order", "edition").first()
        if not enrollment:
            raise NotFound()
        record("staff_participant_id_viewed", enrollment, request.user)
        return Response(card_data(enrollment))

    def post(self, request, enrollment_id):
        action = request.data.get("action")
        permission = "can_review_dic_enrollment_sources" if action == "review_source" else "can_manage_dic_ids"
        if not _can(request.user, permission):
            raise PermissionDenied()
        reason = request.data.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 240:
            raise ValidationError("Use a reason of up to 240 characters.")
        if not CampEnrollment.objects.filter(pk=enrollment_id).exists():
            raise NotFound()
        if action == "review_source":
            if not reason:
                raise ValidationError("A review reason is required.")
            with transaction.atomic():
                initial = CampEnrollment.objects.get(pk=enrollment_id)
                # Same identity lock as enrollment creation and ID commands.
                Participant.objects.select_for_update().get(pk=initial.participant_id)
                enrollment = CampEnrollment.objects.select_for_update().get(pk=enrollment_id)
                items = list(RegistrationOrderItem.objects.filter(participant=enrollment.participant, order__edition=enrollment.edition).select_related("order"))
                chosen = next((i for i in items if i.pk == request.data.get("source_item_id")), None)
                restriction = request.data.get("restriction_reason", "")
                if not chosen or not isinstance(restriction, str) or len(restriction) > 240:
                    raise ValidationError("Choose a matching source and a restriction of up to 240 characters.")
                enrollment.source_item = chosen
                enrollment.source_review_fingerprint = source_fingerprint(items)
                enrollment.restriction_reason = restriction
                enrollment.full_clean()
                enrollment.save(update_fields=("source_item", "source_review_fingerprint", "restriction_reason"))
                for issue in enrollment.id_issues.filter(revoked_at__isnull=True):
                    issue.revoked_at = timezone.now()
                    issue.revoked_by = request.user
                    issue.save(update_fields=("revoked_at", "revoked_by"))
                    record("participant_id_revoked", enrollment, request.user, issue=str(issue.pk), reason="Enrollment source/restriction review")
                record("enrollment_source_reviewed", enrollment, request.user, source_item_id=chosen.pk, reason=reason, restricted=bool(restriction))
        elif action in ("issue", "reissue", "revoke"):
            id_command(enrollment_id, action, request.user, reason)
        else:
            raise ValidationError("Choose issue, reissue, revoke or review_source.")
        return Response(id_summary(CampEnrollment.objects.select_related("participant", "source_item__order", "edition").get(pk=enrollment_id)))
