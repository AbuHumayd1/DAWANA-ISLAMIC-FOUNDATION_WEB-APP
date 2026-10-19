import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.negotiation import DefaultContentNegotiation

from .allocation import paid_participants, unallocated_paid_participants
from .models import (
    CampEdition,
    DICAdminAuditEvent,
    House,
    HouseAllocation,
    Participant,
    PaymentAttempt,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)
from .pricing import (
    PricingConfigurationError,
    current_order_prices,
    revision_matches_current,
)
from .operations_exports import (
    create_word_report,
    registration_export_rows,
    spreadsheet_safe,
)


def _can(user, codename):
    return user.is_superuser or user.has_perm(f"dic.{codename}")


def _verified_order_queryset(queryset):
    return queryset.filter(
        status=RegistrationOrder.Status.CONFIRMED,
        payment_status=RegistrationOrder.PaymentStatus.PAID,
        payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
    ).distinct()


def _order_needs_repricing(order):
    if order.payment_status == RegistrationOrder.PaymentStatus.PAID:
        return False
    try:
        prices = current_order_prices(order)
    except PricingConfigurationError:
        return True
    return not revision_matches_current(order.current_price_revision, prices)


def _edition_from_request(request):
    edition_id = request.query_params.get("edition")
    editions = CampEdition.objects.all()
    if edition_id:
        try:
            return editions.get(pk=int(edition_id))
        except (ValueError, CampEdition.DoesNotExist) as exc:
            raise ValidationError({"edition": "Select a valid camp edition."}) from exc
    active = editions.filter(is_active=True).first()
    return active or editions.order_by("-year").first()


def _base_orders(edition):
    queryset = RegistrationOrder.objects.select_related(
        "edition",
        "primary_registrant",
        "current_price_revision",
    ).prefetch_related(
        "items__participant",
        "items__category",
        "items__participant__house_allocations__house",
        "payment_attempts",
        "price_revisions__items",
        "recovery_challenges__grants",
    )
    return queryset.filter(edition=edition) if edition else queryset.none()


def _apply_order_filters(queryset, params, user, export_limit=None):
    for parameter, field in (
        ("status", "status"),
        ("payment_status", "payment_status"),
    ):
        value = params.get(parameter)
        if value:
            if value not in dict(
                RegistrationOrder._meta.get_field(field).choices
            ):
                raise ValidationError({parameter: "Select a valid filter value."})
            queryset = queryset.filter(**{field: value})
    category = params.get("category")
    if category:
        try:
            queryset = queryset.filter(items__category_id=int(category))
        except ValueError as exc:
            raise ValidationError({"category": "Select a valid category."}) from exc
    house = params.get("house")
    if house:
        try:
            house = int(house)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"house": "Select a valid house."}) from exc
        queryset = queryset.filter(
            items__participant__house_allocations__house_id=house,
            items__participant__house_allocations__status=HouseAllocation.Status.ALLOCATED,
        )
    for parameter, lookup in (("date_from", "gte"), ("date_to", "lte")):
        value = params.get(parameter)
        if value:
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {parameter: "Use an ISO date in YYYY-MM-DD format."}
                ) from exc
            queryset = queryset.filter(**{f"created_at__date__{lookup}": parsed})
    query = params.get("q", "").strip()
    if query:
        clauses = Q(public_id__icontains=query) | Q(
            items__participant__full_name__icontains=query
        )
        if _can(user, "can_view_dic_contact_information"):
            clauses |= (
                Q(primary_registrant__full_name__icontains=query)
                | Q(primary_registrant__email__icontains=query)
                | Q(primary_registrant__phone__icontains=query)
                | Q(items__participant__email__icontains=query)
                | Q(items__participant__phone__icontains=query)
            )
        queryset = queryset.filter(clauses)
    if params.get("requiring_repricing") == "true":
        if export_limit and queryset.distinct().count() > export_limit:
            raise ValidationError({"detail": "Limit exports to 5,000 candidate records using filters."})
        queryset = [
            order
            for order in queryset.distinct()
            if _order_needs_repricing(order)
        ]
        return queryset
    return queryset.distinct()


def _verified_payment(order):
    return (
        order.status == RegistrationOrder.Status.CONFIRMED
        and order.payment_status == RegistrationOrder.PaymentStatus.PAID
        and any(
            attempt.status == PaymentAttempt.Status.SUCCESSFUL
            for attempt in order.payment_attempts.all()
        )
    )


def _order_data(order, user, include_detail=False):
    has_contacts = _can(user, "can_view_dic_contact_information")
    successful = _verified_order_queryset(
        RegistrationOrder.objects.filter(pk=order.pk)
    ).exists()
    participants = []
    for item in order.items.all():
        participant = item.participant
        allocations = [
            {
                "edition_year": allocation.edition.year,
                "house": allocation.house.name,
                "status": allocation.status,
            }
            for allocation in participant.house_allocations.all()
            if allocation.status == HouseAllocation.Status.ALLOCATED
        ]
        row = {
            "id": str(participant.pk),
            "name": participant.full_name,
            "category": item.category_name_snapshot,
            "category_id": item.category_id,
            "quoted_fee_ngn": str(item.fee_snapshot_ngn),
            "verified_paid": successful,
            "allocations": allocations,
        }
        if has_contacts:
            row.update(
                {
                    "email": participant.email,
                    "phone": participant.phone,
                    "address": participant.address,
                }
            )
        participants.append(row)

    has_finance = _can(user, "can_view_dic_finance")
    data = {
        "id": str(order.public_id),
        "edition": {"id": order.edition_id, "name": order.edition.name, "year": order.edition.year},
        "status": order.status,
        "payment_status": order.payment_status,
        "verified_paid": successful,
        "created_at": order.created_at.isoformat(),
        "submitted_at": order.submitted_at.isoformat(),
        "participant_count": len(participants),
        "participants": participants,
        "categories": sorted({item.category_name_snapshot for item in order.items.all()}),
        "quoted_total_ngn": str(order.total_amount_ngn),
        "requires_repricing": _order_needs_repricing(order),
        "recovery_status": _recovery_status(order),
    }
    if has_contacts:
        data["registrant"] = {
            "name": order.primary_registrant.full_name,
            "email": order.primary_registrant.email,
            "phone": order.primary_registrant.phone,
        }
    if has_finance and include_detail:
        data["pricing_revisions"] = [
            {
                "revision": revision.revision_number,
                "total_ngn": str(revision.total_amount_ngn),
                "created_at": revision.created_at.isoformat(),
                "accepted_at": revision.accepted_at.isoformat() if revision.accepted_at else None,
                "items": [
                    {
                        "category": item.category_name_snapshot,
                        "price_type": item.price_type,
                        "fee_ngn": str(item.fee_snapshot_ngn),
                    }
                    for item in revision.items.all()
                ],
            }
            for revision in order.price_revisions.all()
        ]
        data["payment_attempts"] = [
            {
                "reference": attempt.reference,
                "status": attempt.status,
                "expected_amount_ngn": str(Decimal(attempt.amount_kobo) / 100),
                "provider_amount_ngn": (
                    str(Decimal(attempt.provider_reported_amount_kobo) / 100)
                    if attempt.provider_reported_amount_kobo is not None
                    else None
                ),
                "currency": attempt.currency,
                "provider_currency": attempt.provider_reported_currency or None,
                "provider_status": attempt.provider_status,
                "provider_paid_at": attempt.provider_paid_at.isoformat()
                if attempt.provider_paid_at
                else None,
                "reconciliation_reason": attempt.failure_code or None,
                "webhook_events": [
                    {
                        "event_type": event.event_type,
                        "status": event.processing_status,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in attempt.webhook_events.all()
                ],
            }
            for attempt in order.payment_attempts.all()
        ]
        data["audit_history"] = [
            {
                "actor": event.actor.get_username() if event.actor else "System",
                "action": event.action,
                "created_at": event.created_at.isoformat(),
                "details": event.details,
            }
            for event in DICAdminAuditEvent.objects.filter(
                Q(target_id=str(order.pk))
                | Q(target_id=str(order.public_id))
            ).select_related("actor")[:50]
        ] if _can(user, "can_view_dic_audit") else []
    return data


def _recovery_status(order):
    latest = order.recovery_challenges.order_by("-created_at").first()
    if latest is None:
        return "No recovery activity"
    if latest.grants.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).exists():
        return "Recovery access issued"
    return latest.get_delivery_status_display()


def _participant_queryset(edition):
    queryset = Participant.objects.prefetch_related(
        "registration_items__order__edition",
        "registration_items__order__payment_attempts",
        "registration_items__category",
        "house_allocations__house",
    )
    if edition:
        queryset = queryset.filter(registration_items__order__edition=edition)
    return queryset.distinct()


def _apply_participant_filters(queryset, params, user, edition=None):
    query = params.get("q", "").strip()
    if query:
        condition = Q(full_name__icontains=query)
        if _can(user, "can_view_dic_contact_information"):
            condition |= Q(email__icontains=query) | Q(phone__icontains=query)
        queryset = queryset.filter(condition)
    items = RegistrationOrderItem.objects.filter(order__edition=edition)
    for parameter in ("category", "house"):
        value = params.get(parameter)
        if value:
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {parameter: "Select a valid filter value."}
                ) from exc
            if parameter == "category":
                items = items.filter(category_id=value)
            else:
                queryset = queryset.filter(pk__in=HouseAllocation.objects.filter(
                    edition=edition, house_id=value, status=HouseAllocation.Status.ALLOCATED,
                ).values("participant_id"))
    payment_status = params.get("payment_status")
    if payment_status:
        if payment_status not in dict(RegistrationOrder.PaymentStatus.choices):
            raise ValidationError(
                {"payment_status": "Select a valid payment status."}
            )
        items = items.filter(order__payment_status=payment_status)
    for parameter, lookup in (("date_from", "gte"), ("date_to", "lte")):
        value = params.get(parameter)
        if value:
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {parameter: "Use an ISO date in YYYY-MM-DD format."}
                ) from exc
            items = items.filter(**{f"order__created_at__date__{lookup}": parsed})
    return queryset.filter(pk__in=items.values("participant_id")).distinct()


def _participant_data(participant, user, edition=None):
    item_query = participant.registration_items.select_related(
        "order",
        "category",
        "order__edition",
    ).order_by("-created_at")
    allocation_query = participant.house_allocations.filter(
        status=HouseAllocation.Status.ALLOCATED,
    ).select_related("house", "edition")
    if edition:
        item_query = item_query.filter(order__edition=edition)
        allocation_query = allocation_query.filter(edition=edition)
    item = item_query.first()
    allocation = allocation_query.first()
    verified = False
    if item:
        verified = _verified_payment(item.order)
    data = {
        "id": str(participant.pk),
        "name": participant.full_name,
        "registration_reference": str(item.order.public_id) if item else None,
        "registration_order_id": str(item.order.public_id) if item else None,
        "registration_date": item.order.created_at.isoformat() if item else None,
        "category": item.category_name_snapshot if item else None,
        "payment_status": item.order.payment_status if item else None,
        "verified_paid": verified,
        "house": allocation.house.name if allocation else None,
        "sex": participant.sex,
        "academic_status": participant.academic_status,
        "occupation": participant.occupation,
        "marital_status": participant.marital_status,
    }
    if user.is_superuser or user.has_perm("dic.can_view_dic_contact_information"):
        data.update(
            {
                "email": participant.email,
                "phone": participant.phone,
                "address": participant.address,
                "date_of_birth": participant.date_of_birth.isoformat(),
                "height_cm": str(participant.height_cm),
                "weight_kg": str(participant.weight_kg),
            }
        )
    return data


def _paginate(queryset, request, serializer):
    try:
        page_number = max(1, int(request.query_params.get("page", "1")))
        page_size = min(100, max(1, int(request.query_params.get("page_size", "25"))))
    except ValueError as exc:
        raise ValidationError({"page": "Page and page_size must be integers."}) from exc
    paginator = Paginator(queryset, page_size)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages or 1)
    return {
        "count": paginator.count,
        "page": page.number,
        "page_size": page_size,
        "pages": paginator.num_pages,
        "results": [serializer(row) for row in page.object_list],
    }


class OperationsSessionPermission:
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and _can(request.user, "can_view_dic_operations")
        )


@ensure_csrf_cookie
@require_GET
def operations_csrf(request):
    response = JsonResponse({"csrfToken": get_token(request)})
    response["Cache-Control"] = "no-store"
    return response


class OperationsLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "dic_ops_login"

    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(username) > 150
            or len(password) > 1024
        ):
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request=request, username=username, password=password)
        if user is None and "@" in username:
            matches = get_user_model().objects.filter(email__iexact=username, is_active=True)
            if matches.count() == 1:
                user = authenticate(
                    request=request,
                    username=matches.get().get_username(),
                    password=password,
                )
        if (
            user is None
            or not user.is_active
            or not _can(user, "can_view_dic_operations")
        ):
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        response = Response(_user_data(user))
        response["Cache-Control"] = "no-store"
        return response


def _user_data(user):
    return {
        "id": user.pk,
        "username": user.get_username(),
        "display_name": user.get_full_name() or user.get_username(),
        "role": "System Administrator" if user.is_superuser else "DIC Operator",
        "can_access_django_admin": bool(
            user.is_staff and (user.is_superuser or user.has_module_perms("dic"))
        ),
        "permissions": {
            "operations": _can(user, "can_view_dic_operations"),
            "finance": _can(user, "can_view_dic_finance"),
            "audit": _can(user, "can_view_dic_audit"),
            "contact_information": _can(user, "can_view_dic_contact_information"),
            "export_reports": _can(user, "can_export_dic_reports"),
            "export_contacts": _can(user, "can_export_dic_contact_information"),
            "ids": _can(user, "can_view_dic_ids"),
            "manage_ids": _can(user, "can_manage_dic_ids"),
            "review_id_sources": _can(user, "can_review_dic_enrollment_sources"),
        },
    }


class OperationsBaseView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, OperationsSessionPermission)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class OperationsLogoutView(OperationsBaseView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OperationsMeView(OperationsBaseView):
    def get(self, request):
        return Response(_user_data(request.user))


class OperationsFiltersView(OperationsBaseView):
    def get(self, request):
        edition = _edition_from_request(request)
        return Response(
            {
                "edition": {
                    "id": edition.pk,
                    "name": edition.name,
                    "year": edition.year,
                }
                if edition
                else None,
                "categories": list(
                    RegistrationCategory.objects.filter(
                        edition=edition,
                        is_active=True,
                    )
                    .order_by("name")
                    .values("id", "name")
                )
                if edition
                else [],
                "houses": list(
                    House.objects.filter(edition=edition)
                    .order_by("name")
                    .values("id", "name")
                )
                if edition
                else [],
            }
        )


class OperationsDashboardView(OperationsBaseView):
    def get(self, request):
        try:
            days = int(request.query_params.get("days", "14"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"days": "Choose 7, 14 or 30 days."}) from exc
        if days not in (7, 14, 30):
            raise ValidationError({"days": "Choose 7, 14 or 30 days."})
        edition = _edition_from_request(request)
        orders = _base_orders(edition)
        items = RegistrationOrderItem.objects.filter(order__edition=edition)
        verified_orders = _verified_order_queryset(orders)
        unpaid_orders = orders.filter(
            payment_status__in=(
                RegistrationOrder.PaymentStatus.PENDING,
                RegistrationOrder.PaymentStatus.FAILED,
            )
        ).exclude(status=RegistrationOrder.Status.CANCELLED)

        attention = []
        repricing_ids = []
        for order in unpaid_orders:
            if _order_needs_repricing(order):
                repricing_ids.append(order.pk)
                attention.append(
                    {
                        "type": "repricing",
                        "order_id": str(order.public_id),
                        "reference": str(order.public_id),
                        "message": "Pending order requires acceptance of the current price.",
                    }
                )

        reconciliation_count = None
        if _can(request.user, "can_view_dic_finance"):
            reconciliation_count = PaymentAttempt.objects.filter(
                order__edition=edition,
                status__in=(
                    PaymentAttempt.Status.AMOUNT_MISMATCH,
                    PaymentAttempt.Status.RECONCILIATION_REQUIRED,
                ),
            ).count()
            unverified_paid = orders.filter(
                payment_status=RegistrationOrder.PaymentStatus.PAID,
            ).exclude(
                payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
            )[:10]
            for order in unverified_paid:
                attention.append(
                    {
                        "type": "payment_review",
                        "order_id": str(order.public_id),
                        "reference": str(order.public_id),
                        "message": "Paid status has no successful verified attempt.",
                    }
                )
            for attempt in PaymentAttempt.objects.filter(
                order__edition=edition,
                status__in=(
                    PaymentAttempt.Status.AMOUNT_MISMATCH,
                    PaymentAttempt.Status.RECONCILIATION_REQUIRED,
                ),
            ).select_related("order")[:10]:
                attention.append(
                    {
                        "type": "reconciliation",
                        "order_id": str(attempt.order.public_id),
                        "reference": str(attempt.order.public_id),
                        "message": "Payment attempt needs finance reconciliation.",
                    }
                )

        active_allocations = HouseAllocation.objects.filter(
            edition=edition,
            status=HouseAllocation.Status.ALLOCATED,
        )
        house_counts = list(
            House.objects.filter(edition=edition)
            .annotate(
                allocated_count=Count(
                    "allocations",
                    filter=Q(allocations__status=HouseAllocation.Status.ALLOCATED),
                    distinct=True,
                )
            )
            .values("id", "name", "allocated_count", "capacity", "status")
            .order_by("name")
        ) if edition else []
        category_counts = list(
            items.values("category_name_snapshot")
            .annotate(participants=Count("participant_id", distinct=True))
            .order_by("category_name_snapshot")
        )
        distribution = list(
            orders.values("payment_status")
            .annotate(orders=Count("pk", distinct=True))
            .order_by("payment_status")
        )
        activity = list(
            orders.filter(created_at__date__gte=timezone.localdate() - timedelta(days=days - 1))
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(orders=Count("pk", distinct=True), participants=Count("items", distinct=True))
            .order_by("day")
        )
        registered_participants = items.values("participant_id").distinct().count()
        active_allocated_participants = active_allocations.values("participant_id").distinct().count()
        eligible_unallocated = (
            unallocated_paid_participants(edition).count() if edition else 0
        )
        recent = orders.order_by("-created_at")[:8]
        for order in recent:
            if order.payment_status == RegistrationOrder.PaymentStatus.PAID and not _verified_payment(order):
                attention.append(
                    {
                        "type": "payment_review",
                        "order_id": str(order.public_id),
                        "reference": str(order.public_id),
                        "message": "Payment status needs verification review.",
                    }
                )
        return Response(
            {
                "edition": {
                    "id": edition.pk,
                    "name": edition.name,
                    "year": edition.year,
                    "registration_status": edition.registration_status,
                    "camp_start_date": edition.camp_start_date.isoformat(),
                    "camp_end_date": edition.camp_end_date.isoformat(),
                    "venue": edition.venue_name,
                }
                if edition
                else None,
                "metrics": {
                    "orders": orders.count(),
                    "participants": registered_participants,
                    "verified_paid_orders": verified_orders.count(),
                    "verified_paid_participants": items.filter(
                        order__in=verified_orders.values("pk")
                    ).values("participant_id").distinct().count(),
                    "pending_unpaid_orders": unpaid_orders.count(),
                    "requiring_repricing": len(repricing_ids),
                    "reconciliation_cases": reconciliation_count,
                    "eligible_unallocated_participants": eligible_unallocated,
                    "allocated_participants": active_allocated_participants,
                },
                "category_distribution": category_counts,
                "payment_distribution": distribution,
                "house_distribution": house_counts,
                "registration_activity": [
                    {
                        "date": row["day"].isoformat(),
                        "orders": row["orders"],
                        "participants": row["participants"],
                    }
                    for row in activity
                ],
                "recent_registrations": [
                    {
                        "reference": str(order.public_id),
                        "created_at": order.created_at.isoformat(),
                        "status": order.status,
                        "payment_status": order.payment_status,
                        "participants": order.items.count(),
                    }
                    for order in recent
                ],
                "attention": attention[:20],
                "can_view_finance": _can(request.user, "can_view_dic_finance"),
                "can_view_audit": _can(request.user, "can_view_dic_audit"),
            }
        )


class OperationsRegistrationListView(OperationsBaseView):
    def get(self, request):
        edition = _edition_from_request(request)
        orders = _apply_order_filters(
            _base_orders(edition),
            request.query_params,
            request.user,
        )
        return Response(
            _paginate(orders, request, lambda order: _order_data(order, request.user))
        )


class OperationsRegistrationDetailView(OperationsBaseView):
    def get(self, request, public_id):
        edition = _edition_from_request(request)
        order = _apply_order_filters(
            _base_orders(edition).filter(public_id=public_id),
            request.query_params,
            request.user,
        ).first()
        if order is None:
            return Response({"detail": "Registration not found."}, status=404)
        return Response(_order_data(order, request.user, include_detail=True))


class OperationsParticipantListView(OperationsBaseView):
    def get(self, request):
        edition = _edition_from_request(request)
        participants = _apply_participant_filters(
            _participant_queryset(edition),
            request.query_params,
            request.user,
            edition,
        )
        ordering = request.query_params.get("ordering", "name")
        ordering_map = {
            "name": "full_name",
            "-name": "-full_name",
            "date": "registration_items__order__created_at",
            "-date": "-registration_items__order__created_at",
        }
        if ordering not in ordering_map:
            raise ValidationError({"ordering": "Choose a supported sort order."})
        return Response(
            _paginate(
                participants.order_by(ordering_map[ordering], "pk"),
                request,
                lambda row: _participant_data(row, request.user, edition),
            )
        )


class OperationsParticipantDetailView(OperationsBaseView):
    def get(self, request, participant_id):
        edition = _edition_from_request(request)
        participant = _participant_queryset(edition).filter(pk=participant_id).first()
        if participant is None:
            return Response({"detail": "Participant not found."}, status=404)
        data = _participant_data(participant, request.user, edition)
        data["registrations"] = [
            _order_data(item.order, request.user)
            for item in participant.registration_items.select_related(
                "order__edition",
                "order__primary_registrant",
                "order__current_price_revision",
            )
            .filter(order__edition=edition)
            .order_by("-created_at")
        ]
        return Response(data)


class OperationsPaymentListView(OperationsBaseView):
    def get(self, request):
        if not _can(request.user, "can_view_dic_finance"):
            raise PermissionDenied
        edition = _edition_from_request(request)
        attempts = PaymentAttempt.objects.select_related(
            "order__edition",
            "order__primary_registrant",
        ).prefetch_related("webhook_events")
        if edition:
            attempts = attempts.filter(order__edition=edition)
        state = request.query_params.get("status")
        if state:
            if state not in dict(PaymentAttempt.Status.choices):
                raise ValidationError({"status": "Select a valid payment status."})
            attempts = attempts.filter(status=state)
        query = request.query_params.get("q", "").strip()
        if query:
            attempts = attempts.filter(
                Q(order__public_id__icontains=query)
                | Q(reference__icontains=query)
                | Q(provider_transaction_id__icontains=query)
            )
        if request.query_params.get("category"):
            try:
                category_id = int(request.query_params["category"])
            except ValueError as exc:
                raise ValidationError(
                    {"category": "Select a valid category."}
                ) from exc
            attempts = attempts.filter(order__items__category_id=category_id)
        if request.query_params.get("house"):
            try:
                house_id = int(request.query_params["house"])
            except ValueError as exc:
                raise ValidationError({"house": "Select a valid house."}) from exc
            attempts = attempts.filter(
                order__items__participant__house_allocations__house_id=house_id,
                order__items__participant__house_allocations__status=HouseAllocation.Status.ALLOCATED,
            )
        for parameter, lookup in (("date_from", "gte"), ("date_to", "lte")):
            value = request.query_params.get(parameter)
            if value:
                try:
                    parsed = date.fromisoformat(value)
                except (TypeError, ValueError) as exc:
                    raise ValidationError(
                        {parameter: "Use an ISO date in YYYY-MM-DD format."}
                    ) from exc
                attempts = attempts.filter(**{f"created_at__date__{lookup}": parsed})

        def serialize(attempt):
            return {
                "reference": attempt.reference,
                "order_reference": str(attempt.order.public_id),
                "status": attempt.status,
                "verified_paid": _verified_payment(attempt.order),
                "expected_amount_ngn": str(Decimal(attempt.amount_kobo) / 100),
                "provider_amount_ngn": (
                    str(Decimal(attempt.provider_reported_amount_kobo) / 100)
                    if attempt.provider_reported_amount_kobo is not None
                    else None
                ),
                "currency": attempt.currency,
                "provider_currency": attempt.provider_reported_currency or None,
                "provider_status": attempt.provider_status or None,
                "provider_paid_at": attempt.provider_paid_at.isoformat()
                if attempt.provider_paid_at
                else None,
                "reconciliation_reason": attempt.failure_code or None,
                "created_at": attempt.created_at.isoformat(),
                "verified_at": attempt.verified_at.isoformat()
                if attempt.verified_at
                else None,
                "webhook_events": [
                    {
                        "event_type": event.event_type,
                        "status": event.processing_status,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in attempt.webhook_events.all()
                ],
            }

        return Response(_paginate(attempts, request, serialize))


class OperationsHouseView(OperationsBaseView):
    def get(self, request):
        edition = _edition_from_request(request)
        if edition is None:
            return Response({"edition": None, "houses": [], "allocations": [], "eligible_unallocated": 0})
        houses = House.objects.filter(edition=edition).annotate(
            allocated_count=Count(
                "allocations",
                filter=Q(allocations__status=HouseAllocation.Status.ALLOCATED),
                distinct=True,
            )
        ).order_by("name")
        allocations = HouseAllocation.objects.filter(edition=edition).select_related(
            "participant",
            "house",
            "allocated_by",
            "previous_allocation",
        )
        return Response(
            {
                "edition": {"id": edition.pk, "name": edition.name, "year": edition.year},
                "eligible_unallocated": unallocated_paid_participants(edition).count(),
                "houses": [
                    {
                        "id": house.pk,
                        "name": house.name,
                        "gender": house.gender,
                        "purpose": house.purpose,
                        "capacity": house.capacity,
                        "status": house.status,
                        "allocated_count": house.allocated_count,
                    }
                    for house in houses
                ],
                "allocations": _paginate(
                    allocations,
                    request,
                    lambda allocation: {
                        "participant": allocation.participant.full_name,
                        "participant_id": str(allocation.participant_id),
                        "house": allocation.house.name,
                        "status": allocation.status,
                        "allocated_at": allocation.allocated_at.isoformat(),
                        "allocated_by": allocation.allocated_by.get_username()
                        if allocation.allocated_by
                        else None,
                        "reason": allocation.change_reason or allocation.resolution_reason or None,
                        "verified_eligible": paid_participants(edition)
                        .filter(pk=allocation.participant_id)
                        .exists(),
                    },
                ),
            }
        )


class OperationsActivityView(OperationsBaseView):
    def get(self, request):
        if not _can(request.user, "can_view_dic_audit"):
            raise PermissionDenied
        queryset = DICAdminAuditEvent.objects.select_related("actor").all()
        return Response(
            _paginate(
                queryset,
                request,
                lambda event: {
                    "id": event.pk,
                    "actor": event.actor.get_username() if event.actor else "System",
                    "action": event.action,
                    "target_type": event.target_type,
                    "target_id": event.target_id,
                    "details": event.details,
                    "created_at": event.created_at.isoformat(),
                },
            )
        )


def _report_rows(report_type, queryset, user, edition=None):
    include_contacts = _can(user, "can_export_dic_contact_information")
    include_finance = _can(user, "can_view_dic_finance")
    if report_type == "registrations":
        return registration_export_rows(queryset, include_contacts)
    if report_type == "participants":
        headers = ["Participant ID", "Name", "Registration reference", "Category", "Payment status", "Verified paid", "House", "Registration date"]
        if include_contacts:
            headers.extend(("Email", "Phone", "Address"))
        rows = []
        for participant in queryset:
            item = participant.registration_items.filter(order__edition=edition).select_related("order", "category").first()
            allocation = participant.house_allocations.filter(
                status=HouseAllocation.Status.ALLOCATED, edition=edition,
            ).select_related("house").first()
            row = [
                str(participant.pk),
                participant.full_name,
                str(item.order.public_id) if item else "",
                item.category_name_snapshot if item else "",
                item.order.payment_status if item else "",
                "Yes" if item and _verified_payment(item.order) else "No",
                allocation.house.name if allocation else "",
                item.order.created_at.isoformat() if item else "",
            ]
            if include_contacts:
                row.extend((participant.email, participant.phone, participant.address))
            rows.append(row)
        return headers, rows
    if report_type == "payments":
        if not include_finance:
            raise PermissionDenied
        headers = ["Registration reference", "Payment reference", "Expected amount (NGN)", "Provider amount (NGN)", "Currency", "Provider currency", "Attempt status", "Verified paid", "Provider completion time", "Reconciliation reason"]
        rows = [
            [
                str(attempt.order.public_id),
                attempt.reference,
                str(Decimal(attempt.amount_kobo) / 100),
                str(Decimal(attempt.provider_reported_amount_kobo) / 100) if attempt.provider_reported_amount_kobo is not None else "",
                attempt.currency,
                attempt.provider_reported_currency,
                attempt.status,
                "Yes" if _verified_payment(attempt.order) else "No",
                attempt.provider_paid_at.isoformat() if attempt.provider_paid_at else "",
                attempt.failure_code,
            ]
            for attempt in queryset
        ]
        return headers, rows
    if report_type == "categories":
        return (
            ["Edition", "Category", "Active", "Regular fee (NGN)", "Early-bird fee (NGN)"],
            [
                [
                    category.edition.name,
                    category.name,
                    "Yes" if category.is_active else "No",
                    str(category.fee_ngn) if category.fee_ngn is not None else "",
                    str(category.early_bird_fee_ngn) if category.early_bird_fee_ngn is not None else "",
                ]
                for category in queryset
            ],
        )
    if report_type == "houses":
        return (
            ["Edition", "House", "Status", "Capacity", "Allocated participants"],
            [
                [
                    house.edition.name,
                    house.name,
                    house.status,
                    house.capacity if house.capacity is not None else "",
                    house.allocated_count,
                ]
                for house in queryset
            ],
        )
    if report_type == "attention":
        return (
            ["Registration reference", "Payment status", "Issue"],
            [
                [
                    str(order.public_id),
                    order.payment_status,
                    "Repricing required"
                    if _order_needs_repricing(order)
                    else "Payment status requires review",
                ]
                for order in queryset
            ],
        )
    raise ValidationError({"report": "Choose a supported report type."})


class ReportContentNegotiation(DefaultContentNegotiation):
    def filter_renderers(self, renderers, format):
        # The report endpoint owns these download formats; errors remain JSON.
        if format in ("csv", "docx"):
            return renderers
        return super().filter_renderers(renderers, format)


class OperationsReportView(OperationsBaseView):
    content_negotiation_class = ReportContentNegotiation
    def get(self, request):
        if not _can(request.user, "can_export_dic_reports"):
            raise PermissionDenied
        edition = _edition_from_request(request)
        report_type = request.query_params.get("report", "registrations")
        export_format = request.query_params.get("format", "csv").lower()
        if export_format not in ("csv", "docx"):
            raise ValidationError({"format": "Choose csv or docx."})
        params = request.query_params.copy()
        for key in ("format", "report"):
            params.pop(key, None)
        order_params = params.copy()
        if report_type == "payments":
            order_params.pop("status", None)
        orders = _apply_order_filters(
            _base_orders(edition),
            order_params,
            request.user,
            export_limit=5000,
        )
        if report_type == "registrations":
            queryset = orders
        elif report_type == "participants":
            queryset = _apply_participant_filters(
                _participant_queryset(edition),
                params,
                request.user,
                edition,
            )
        elif report_type == "payments":
            if not _can(request.user, "can_view_dic_finance"):
                raise PermissionDenied
            queryset = PaymentAttempt.objects.filter(order__edition=edition).select_related("order", "order__edition")
            for parameter, lookup in (("category", "order__items__category_id"), ("house", "order__items__participant__house_allocations__house_id")):
                if params.get(parameter):
                    try:
                        value = int(params[parameter])
                    except (TypeError, ValueError) as exc:
                        raise ValidationError({parameter: "Select a valid filter."}) from exc
                    queryset = queryset.filter(**{lookup: value})
            if params.get("house"):
                queryset = queryset.filter(order__items__participant__house_allocations__edition=edition, order__items__participant__house_allocations__status=HouseAllocation.Status.ALLOCATED)
            if params.get("payment_status"):
                queryset = queryset.filter(order__payment_status=params["payment_status"])
            queryset = queryset.distinct()
            if params.get("status"):
                if params["status"] not in dict(PaymentAttempt.Status.choices):
                    raise ValidationError({"status": "Select a valid payment status."})
                queryset = queryset.filter(status=params["status"])
            if params.get("q"):
                query = params["q"].strip()
                queryset = queryset.filter(
                    Q(order__public_id__icontains=query)
                    | Q(reference__icontains=query)
                    | Q(provider_transaction_id__icontains=query)
                )
            for parameter, lookup in (("date_from", "gte"), ("date_to", "lte")):
                value = params.get(parameter)
                if value:
                    try:
                        parsed = date.fromisoformat(value)
                    except (TypeError, ValueError) as exc:
                        raise ValidationError(
                            {parameter: "Use an ISO date in YYYY-MM-DD format."}
                        ) from exc
                    queryset = queryset.filter(
                        **{f"created_at__date__{lookup}": parsed}
                    )
        elif report_type == "categories":
            queryset = RegistrationCategory.objects.filter(edition=edition).select_related("edition")
        elif report_type == "houses":
            queryset = House.objects.filter(edition=edition).annotate(
                allocated_count=Count(
                    "allocations",
                    filter=Q(allocations__status=HouseAllocation.Status.ALLOCATED),
                    distinct=True,
                )
            ).select_related("edition")
        elif report_type == "attention":
            if isinstance(orders, list):
                orders = RegistrationOrder.objects.filter(pk__in=[order.pk for order in orders])
            queryset = orders.filter(
                Q(payment_status=RegistrationOrder.PaymentStatus.PAID)
                | Q(payment_status__in=(RegistrationOrder.PaymentStatus.PENDING, RegistrationOrder.PaymentStatus.FAILED))
            )
            if queryset.count() > 5000:
                raise ValidationError({"detail": "Limit exports to 5,000 candidate records using filters."})
            queryset = [order for order in queryset if _order_needs_repricing(order) or (order.payment_status == RegistrationOrder.PaymentStatus.PAID and not _verified_payment(order))]
        else:
            raise ValidationError({"report": "Choose a supported report type."})

        if not isinstance(queryset, list) and queryset.count() > 5000:
            raise ValidationError({"detail": "Limit exports to 5,000 records using filters."})
        queryset = list(queryset[:5001])
        if len(queryset) > 5000:
            raise ValidationError({"detail": "Limit exports to 5,000 records using filters."})
        headers, rows = _report_rows(report_type, queryset, request.user, edition)
        if report_type == "attention":
            for row, order in zip(rows, queryset):
                if _order_needs_repricing(order):
                    row[2] = "Repricing required"
                else:
                    row[2] = "Payment status requires review"
        safe_rows = [[spreadsheet_safe(value) for value in row] for row in rows]
        filter_values = {
            key: request.query_params.get(key)
            for key in ("edition", "status", "payment_status", "category", "house", "date_from", "date_to", "q")
            if request.query_params.get(key)
        }
        details = {
            "report_type": report_type,
            "format": export_format,
            "filters": filter_values,
            "record_count": len(safe_rows),
            "edition_id": edition.pk if edition else None,
            "contact_information_included": _can(request.user, "can_export_dic_contact_information") and report_type in ("registrations", "participants"),
        }
        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        filename = f"dic-{report_type}-{timestamp}"
        if export_format == "csv":
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(headers)
            writer.writerows(safe_rows)
            response = HttpResponse(
                "\ufeff" + buffer.getvalue(),
                content_type="text/csv; charset=utf-8",
            )
            extension = "csv"
        else:
            content = create_word_report(
                f"DIC {report_type.replace('_', ' ').title()} Report",
                edition.name if edition else None,
                filter_values,
                headers,
                safe_rows,
            )
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            extension = "docx"
        DICAdminAuditEvent.objects.create(
            actor=request.user,
            action="operations_report_export",
            target_type=report_type,
            target_id="",
            details=details,
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.{extension}"'
        response["Cache-Control"] = "no-store"
        return response
