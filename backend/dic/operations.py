from collections import defaultdict

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, OuterRef, Q
from django.shortcuts import render
from django.urls import reverse

from .models import (
    CampEdition,
    HouseAllocation,
    PaymentAttempt,
    RegistrationOrder,
    RegistrationOrderItem,
)
from .pricing import (
    PricingConfigurationError,
    current_order_prices,
    revision_matches_current,
)


def operations_dashboard(request):
    if not request.user.has_perm("dic.can_view_dic_operations"):
        raise PermissionDenied

    verified_paid = RegistrationOrder.objects.filter(
        payment_status=RegistrationOrder.PaymentStatus.PAID,
        status=RegistrationOrder.Status.CONFIRMED,
        payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
    ).distinct()
    unpaid = RegistrationOrder.objects.filter(
        payment_status__in=(
            RegistrationOrder.PaymentStatus.PENDING,
            RegistrationOrder.PaymentStatus.FAILED,
        )
    ).exclude(status=RegistrationOrder.Status.CANCELLED)
    successful_attempt = PaymentAttempt.objects.filter(
        order_id=OuterRef("pk"),
        status=PaymentAttempt.Status.SUCCESSFUL,
    )
    unverified_paid = (
        RegistrationOrder.objects.filter(
            payment_status=RegistrationOrder.PaymentStatus.PAID,
        )
        .annotate(has_successful_attempt=Exists(successful_attempt))
        .filter(
            Q(
                status__in=(
                    RegistrationOrder.Status.SUBMITTED,
                    RegistrationOrder.Status.CANCELLED,
                )
            )
            | Q(has_successful_attempt=False)
        )
    )

    needs_attention = defaultdict(set)
    for order_id in unverified_paid.values_list("pk", flat=True):
        needs_attention[order_id].add("Registration status requires review")
    reconciliation_order_ids = set()
    if request.user.has_perm("dic.can_view_dic_finance"):
        reconciliation_order_ids = set(
            PaymentAttempt.objects.filter(
                status__in=(
                    PaymentAttempt.Status.AMOUNT_MISMATCH,
                    PaymentAttempt.Status.RECONCILIATION_REQUIRED,
                )
            ).values_list("order_id", flat=True)
        )
        for order_id in reconciliation_order_ids:
            needs_attention[order_id].add("Payment reconciliation")

    for order in unpaid.select_related(
        "edition",
        "current_price_revision",
    ).prefetch_related(
        "items__category",
        "current_price_revision__items",
    ):
        try:
            prices = current_order_prices(order)
        except PricingConfigurationError:
            needs_attention[order.pk].add("Pricing configuration needs review")
            continue
        if not revision_matches_current(order.current_price_revision, prices):
            needs_attention[order.pk].add("Repricing required before checkout")

    attention_ids = set(needs_attention)
    attention_orders = (
        RegistrationOrder.objects.filter(pk__in=attention_ids)
        .select_related("edition")
        .order_by("-created_at")[:10]
    )
    attention_rows = [
        {
            "order": order,
            "reasons": sorted(needs_attention[order.pk]),
            "url": reverse("admin:dic_registrationorder_change", args=(order.pk,)),
        }
        for order in attention_orders
    ]

    category_counts = (
        RegistrationOrderItem.objects.values(
            "order__edition__year",
            "category_name_snapshot",
        )
        .annotate(
            registrations=Count("pk"),
            individual_participants=Count("participant_id", distinct=True),
        )
        .order_by("order__edition__year", "category_name_snapshot")
    )
    house_counts = (
        HouseAllocation.objects.filter(
            status=HouseAllocation.Status.ALLOCATED,
        )
        .values("edition__year", "house__name")
        .annotate(participants=Count("participant_id", distinct=True))
        .order_by("edition__year", "house__name")
    )

    context = {
        **admin.site.each_context(request),
        "title": "DIC operations",
        "report_editions": CampEdition.objects.order_by("-year"),
        "total_orders": RegistrationOrder.objects.count(),
        "individual_participants": RegistrationOrderItem.objects.values(
            "participant_id"
        ).distinct().count(),
        "verified_paid_orders": verified_paid.count(),
        "verified_paid_participants": RegistrationOrderItem.objects.filter(
            order__in=verified_paid.values("pk")
        ).values("participant_id").distinct().count(),
        "unpaid_orders": unpaid.count(),
        "category_counts": category_counts,
        "house_counts": house_counts,
        "attention_rows": attention_rows,
        "attention_count": len(attention_ids),
        "can_view_finance": request.user.has_perm("dic.can_view_dic_finance"),
        "order_list_url": reverse("admin:dic_registrationorder_changelist"),
        "participant_list_url": reverse("admin:dic_participant_changelist"),
        "allocation_list_url": reverse("admin:dic_houseallocation_changelist"),
        "payment_list_url": reverse("admin:dic_paymentattempt_changelist"),
        "audit_list_url": reverse("admin:dic_dicadminauditevent_changelist"),
        "can_view_audit": request.user.has_perm("dic.can_view_dic_audit"),
    }
    if context["can_view_finance"]:
        context["reconciliation_count"] = len(reconciliation_order_ids)
        context["unverified_paid_status_count"] = unverified_paid.count()
    return render(request, "admin/dic/operations_dashboard.html", context)
