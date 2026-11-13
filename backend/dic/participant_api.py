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
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.settings import APISettings
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from .media_delivery import safe_media

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
    raw = order.primary_registrant.email if channel in ("email", "username") else order.primary_registrant.phone
    try:
        normalized = normalize_email(raw) if channel in ("email", "username") else normalize_phone(raw)
    except (ValueError, AttributeError):
        return False
    # Username accounts retain a contact snapshot for change/revocation checks;
    # this is not contact ownership proof and cannot be used as an OTP channel.
    digest_channel = "email" if channel == "username" else channel
    return hmac.compare_digest(_contact_digest(digest_channel, normalized), contact_hash)


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
    from .portal_accounts import ACCOUNT_TOKEN_PREFIX, enabled
    if token.startswith(ACCOUNT_TOKEN_PREFIX) and not enabled():
        raise AuthenticationFailed("Account sign-in is disabled. Please verify your booking contact.")
    if not token or len(token) > 256:
        raise AuthenticationFailed("Your participant session has expired. Please verify again.")
    query = ParticipantPortalGrant.objects.select_for_update() if lock else ParticipantPortalGrant.objects
    grant = query.filter(credential_digest=digest_value(token), revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not grant:
        raise AuthenticationFailed("Your participant session has expired. Please verify again.")
    from .portal_accounts import account_session
    account_session(grant)
    # All participant readers share this boundary, including OTP-only grants.
    orders = scoped_orders(grant)
    if not orders:
        raise PermissionDenied('No currently eligible registration is available. Use booking recovery or contact DIC staff.')
    # Read views reuse this authorization result only within the current request.
    # No entitlements are cached across requests or after a mutation.
    grant.authorized_orders = orders
    return grant


def scoped_orders(grant):
    orders = RegistrationOrder.objects.filter(
        participantportalscope__grant=grant, participantportalscope__revoked_at__isnull=True,
        access_token_revoked_at__isnull=True,
    ).exclude(status="cancelled").select_related("edition", "primary_registrant")
    from .portal_accounts import account_session, linked_orders, booking_eligible
    mapping = account_session(grant)
    allowed = {o.pk for o in linked_orders(mapping.account)} if mapping else None
    return [order for order in orders if (allowed is None or order.pk in allowed)
        and primary_contact_matches(order, grant.channel, grant.contact_digest)
        and (mapping is not None or booking_eligible(order))
        and (order.registration_basis != 'tutor' or order.items.filter(
            enrollments__tutorregistrationauthorization__revoked_at__isnull=True,
            enrollments__tutorregistrationauthorization__redeemed_at__isnull=False).exists())]


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
        from .portal_phase3 import session_seconds
        duration = session_seconds(request.data.get('remember_device', False))
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
                if valid:
                    from .portal_accounts import booking_eligible
                    valid = booking_eligible(order)
                if valid or challenge.attempts >= MAX_CODE_ATTEMPTS:
                    challenge.consumed_at = now
                    challenge.encrypted_delivery_payload = ""
                challenge.save(update_fields=("attempts", "consumed_at", "encrypted_delivery_payload"))
                if valid:
                    ParticipantPortalGrant.objects.filter(credential_digest=digest_value(request.COOKIES.get(COOKIE, "")), revoked_at__isnull=True).update(revoked_at=now)
                    token = secrets.token_urlsafe(32)
                    grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value(token), channel=challenge.channel, contact_digest=challenge.contact_digest, expires_at=now + timedelta(seconds=duration))
                    ParticipantPortalScope.objects.create(grant=grant, order=order)
                    record("participant_portal_authenticated", grant_id=str(grant.pk))
                    failed = False
            if failed:
                record("participant_otp_rejected")
        # Failed-attempt counters commit, rather than roll back on exceptions.
        if failed:
            raise ValidationError(INVALID)
        response = Response({"authenticated": True, "expires_at": grant.expires_at.isoformat()})
        cookie(response, COOKIE, token, duration)
        response.delete_cookie(BROWSER_COOKIE, path=COOKIE_PATH, samesite="Lax")
        return response


class PortalMeView(PortalView):
    def get(self, request):
        grant = authorized_grant(request)
        return Response({"authenticated": True, "expires_at": grant.expires_at.isoformat(), "booking_count": len(grant.authorized_orders)})


class PortalLogoutView(PortalView):
    def post(self, request):
        with transaction.atomic():
            # Sign-out must remain possible after refund, revocation or expiry.
            token = request.COOKIES.get(COOKIE, '')
            grant_id = None
            if token and len(token) <= 256:
                grants = ParticipantPortalGrant.objects.filter(credential_digest=digest_value(token), revoked_at__isnull=True)
                grant_id = grants.values_list('pk', flat=True).first()
                grants.update(revoked_at=timezone.now())
            record("participant_portal_logout", grant_id=str(grant_id) if grant_id else '')
        response = Response(status=204)
        response.delete_cookie(COOKIE, path=COOKIE_PATH, samesite="Lax")
        response.delete_cookie(BROWSER_COOKIE, path=COOKIE_PATH, samesite="Lax")
        return response


class PortalEnrollmentsView(PortalView):
    def get(self, request):
        grant = authorized_grant(request)
        results = []
        for order in grant.authorized_orders:
            participants = []
            for item in order.items.select_related("participant"):
                enrollment = CampEnrollment.objects.filter(participant=item.participant, edition=order.edition, source_item__order=order).select_related("participant", "source_item__order", "edition").first()
                summary = id_summary(enrollment) if enrollment else {"name": item.participant.full_name, "category": item.category_name_snapshot, "id": None, "participant_number": None, "issue": None}
                if not enrollment:
                    # Unsaved candidate keeps reads side-effect free.
                    candidate = CampEnrollment(participant=item.participant, edition=order.edition, source_item=item)
                    summary["eligibility"] = eligibility(candidate)
                summary["registration_item_id"] = item.pk
                from .portal_phase3 import class_assignment
                summary['class_assignment'] = class_assignment(order.registration_basis, item.participant_id, order.edition)
                from .portal_dashboard import camper_operations_summary
                summary.update(camper_operations_summary(item.participant_id,order.edition))
                from .fulfillment import portal_status
                summary['fulfillment'] = portal_status(order)
                participants.append(summary)
            results.append({"reference": str(order.public_id), "edition": order.edition.name, "registration_basis": order.registration_basis, "payment_status": order.payment_status, "status": order.status, "participants": participants})
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
        if any(key in request.data for key in ('action', 'operation')):
            raise PermissionDenied('Participants and guardians cannot issue, replace or revoke IDs.')
        enrollment = ensure_enrollment(item.pk)
        if enrollment.source_item.order_id != item.order_id:
            raise ValidationError("Registration source requires staff review.")
        # Compatibility: this endpoint prepares identity records only. Staff
        # issuance is deliberately separate, even for verified paid bookings.
        record("participant_id_accessed", enrollment, grant_id=str(grant.pk))
        return Response(id_summary(enrollment))


def card_data(enrollment):
    summary = id_summary(enrollment)
    if not summary["eligibility"]["eligible"] or not summary["issue"] or summary["issue"]["status"] != "current":
        raise ValidationError("No currently eligible ID is available. Contact authorized staff for review.")
    edition = enrollment.edition
    allocations = HouseAllocation.objects.filter(participant=enrollment.participant, edition=edition, house__edition=edition, house__status="active", status="allocated").select_related("house")
    house = allocations.first() if allocations.count() == 1 else None
    return {"id": str(enrollment.pk), "name": summary["name"], "participant_number": summary["participant_number"], "category": summary["category"],
            "edition": edition.name, "starts": edition.camp_start_date, "ends": edition.camp_end_date, "venue": edition.venue_name,
            "house": house.house.name if house else None, "version": summary["issue"]["version"],
            "logo_url": settings.DIC_OFFICIAL_LOGO_URL or None, "branding_verified": bool(settings.DIC_OFFICIAL_LOGO_URL)}


class PortalIDView(PortalView):
    def get(self, request, enrollment_id):
        enrollment = authorized_portal_card(request, enrollment_id)
        grant = authorized_grant(request)
        data = card_data(enrollment)
        record("participant_id_viewed", enrollment, grant_id=str(grant.pk))
        return Response(data)


def authorized_portal_card(request, enrollment_id):
    """Reuse verified booking scope; a housing guardian link never expands it."""
    from .models import GuardianRelationship
    from .housing_policy import age_on
    from django.core.exceptions import ValidationError as PolicyError
    grant, enrollment = scoped_enrollment(request, enrollment_id)
    orders = scoped_orders(grant)
    order_ids = [order.pk for order in orders]
    if enrollment.source_item.order.registration_basis == 'tutor':
        if not eligibility(enrollment)['eligible']:
            raise PermissionDenied('Tutor authorization is unavailable.')
        return enrollment
    try:
        from .registration_age import asserted_adult
        from .housing_policy import age_reference
        reference = age_reference(enrollment.edition)
        # A stored adult assertion can exclude the <=5 display/access branch
        # only at an applicable reference date. It grants no guardianship or
        # release authority and does not authorize age-sensitive housing.
        dependent = False if reference and asserted_adult(enrollment.participant, reference) else age_on(enrollment.participant, enrollment.edition) <= 5
    except PolicyError:
        raise ValidationError('Age/guardian details require authorized staff review.')
    if dependent:
        relation = GuardianRelationship.objects.filter(edition=enrollment.edition,
            child=enrollment.participant, status='approved', approved_at__isnull=False,
            approved_by__isnull=False).select_related('guardian').first()
        if not relation:
            raise PermissionDenied('Approved guardian access is required for this dependent ID.')
        try:
            relation.clean()
        except PolicyError:
            raise PermissionDenied('Guardian eligibility requires authorized staff review.')
        guardian = CampEnrollment.objects.filter(participant=relation.guardian, edition=enrollment.edition,
            source_item__order_id__in=order_ids).select_related('source_item__order', 'edition').first()
        if not guardian or not eligibility(guardian)['eligible']:
            raise PermissionDenied('The approved guardian must have eligible access within this verified booking.')
    return enrollment


class CardDownloadNegotiation(DefaultContentNegotiation):
    # This endpoint's ?format=pvc/a6 selects physical card dimensions, not a
    # DRF renderer. Keep normal Accept negotiation, and defer physical-format
    # validation until after booking/enrollment/guardian authorization.
    settings = APISettings({'URL_FORMAT_OVERRIDE': None})


class PortalCardView(PortalView):
    content_negotiation_class = CardDownloadNegotiation

    @safe_media
    def get(self, request, enrollment_id):
        from .identity_views import _render_authorized_cards
        enrollment = authorized_portal_card(request, enrollment_id)
        if request.query_params.get('format') == 'portrait':
            from .portrait_pdf import render_pdf, require_pdf_dependencies
            from .identity_cards import card_context
            from .identity_views import secured
            from django.http import HttpResponse
            require_pdf_dependencies()
            response = HttpResponse(render_pdf([card_context(request, enrollment)]), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="dawana-portrait-id.pdf"'
            return secured(response)
        # No issuance, activation, bulk print or staff URLs; one scoped active ID.
        return _render_authorized_cards(request, [enrollment],
            download=request.query_params.get('download') == '1',
            card_format=request.query_params.get('format', 'pvc'), portal=True)


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
            if not request.user.is_active or not request.user.is_staff:
                raise PermissionDenied('Active authorized source-review staff access is required.')
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
                if (enrollment.source_item.order.registration_basis != chosen.order.registration_basis
                        or (chosen.order.registration_basis == 'tutor' and chosen.pk != enrollment.source_item_id)):
                    raise ValidationError('Tutor and paid registration sources cannot be converted or reassigned.')
                enrollment.source_item = chosen
                enrollment.source_review_fingerprint = source_fingerprint(items)
                enrollment.restriction_reason = restriction
                enrollment.full_clean()
                enrollment.save(update_fields=("source_item", "source_review_fingerprint", "restriction_reason"))
                for issue in enrollment.id_issues.filter(revoked_at__isnull=True):
                    issue.revoked_at = timezone.now()
                    issue.revoked_by = request.user
                    issue.save(update_fields=("revoked_at", "revoked_by"), issuance_actor=request.user)
                    record("participant_id_revoked", enrollment, request.user, issue=str(issue.pk), reason="Enrollment source/restriction review")
                record("enrollment_source_reviewed", enrollment, request.user, source_item_id=chosen.pk, reason=reason, restricted=bool(restriction))
        elif action in ("issue", "reissue", "revoke"):
            from .identity_cards import command
            command(CampEnrollment.objects.get(pk=enrollment_id), action, request.user, reason)
        else:
            raise ValidationError("Choose issue, reissue, revoke or review_source.")
        return Response(id_summary(CampEnrollment.objects.select_related("participant", "source_item__order", "edition").get(pk=enrollment_id)))
