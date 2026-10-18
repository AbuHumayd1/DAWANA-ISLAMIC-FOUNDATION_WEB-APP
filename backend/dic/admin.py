from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .allocation import (
    AllocationError,
    allocation_configuration_fingerprint,
    allocate_participants,
    assign_participant,
    paid_participants,
    release_allocation,
    unallocated_paid_participants,
)
from .models import (
    CampEdition,
    House,
    HouseAllocation,
    PaymentAttempt,
    PaystackWebhookEvent,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
    RegistrationOrderPriceItem,
    RegistrationOrderPriceRevision,
)


class HouseAllocationInline(admin.TabularInline):
    model = HouseAllocation
    extra = 0
    can_delete = False
    fields = (
        "edition",
        "house",
        "status",
        "allocated_at",
        "allocated_by",
        "change_reason",
        "resolution_reason",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class HouseAllocationCreateForm(forms.ModelForm):
    class Meta:
        model = HouseAllocation
        fields = ("edition", "participant", "house", "change_reason")

    def clean(self):
        cleaned = super().clean()
        participant = cleaned.get("participant")
        edition = cleaned.get("edition")
        house = cleaned.get("house")
        if participant and edition and not paid_participants(edition).filter(pk=participant.pk).exists():
            self.add_error("participant", "Participant has no paid registration for this edition.")
        if participant and edition and HouseAllocation.objects.filter(
            participant=participant,
            edition=edition,
            status=HouseAllocation.Status.ALLOCATED,
        ).exists():
            self.add_error("participant", "Participant already has an active allocation.")
        if house and edition and house.edition_id != edition.pk:
            self.add_error("house", "Select a house belonging to the selected edition.")
        if participant and edition and house:
            try:
                HouseAllocation(
                    participant=participant,
                    edition=edition,
                    house=house,
                ).full_clean()
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    self.add_error(field if field in self.fields else None, errors)
        return cleaned


class RegistrationCategoryInline(admin.TabularInline):
    model = RegistrationCategory
    extra = 0
    show_change_link = True
    fields = (
        "name",
        "minimum_age",
        "maximum_age",
        "early_bird_fee_ngn",
        "fee_ngn",
        "is_active",
    )


class HouseInline(admin.TabularInline):
    model = House
    extra = 0
    show_change_link = True
    fields = ("name", "gender", "purpose", "capacity", "status")


class RegistrationOrderItemInline(admin.TabularInline):
    model = RegistrationOrderItem
    extra = 0
    can_delete = False
    fields = (
        "participant",
        "category",
        "category_name_snapshot",
        "fee_snapshot_ngn",
        "participant_snapshot",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class RegistrationOrderPriceRevisionInline(admin.TabularInline):
    model = RegistrationOrderPriceRevision
    extra = 0
    can_delete = False
    fields = (
        "revision_number",
        "total_amount_ngn",
        "early_bird_cutoff_at",
        "created_at",
        "accepted_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CampEdition)
class CampEditionAdmin(admin.ModelAdmin):
    change_form_template = "admin/dic/change_form.html"
    list_display = (
        "name",
        "year",
        "camp_start_date",
        "camp_end_date",
        "registration_status",
        "pricing_status",
        "venue_name",
        "is_active",
        "allocation_strategy",
        "allocation_strategy_approved_at",
    )
    list_filter = ("registration_status", "is_active", "allocation_strategy", "year")
    search_fields = ("name",)
    ordering = ("-year",)
    inlines = (RegistrationCategoryInline, HouseInline)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "year",
                    "is_active",
                    "registration_status",
                    "allocation_strategy",
                )
            },
        ),
        (
            "House allocation approval",
            {
                "fields": (
                    "allocation_strategy_approved_at",
                    "allocation_strategy_approved_by",
                    "allocation_strategy_approval_note",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "camp_start_date",
                    "camp_end_date",
                    "registration_open_date",
                    "registration_close_date",
                    "early_bird_cutoff_at",
                )
            },
        ),
        (
            "Venue and verified directions",
            {
                "fields": (
                    "venue_name",
                    "venue_directions_address",
                    "venue_google_place_id",
                    "venue_latitude",
                    "venue_longitude",
                    "venue_directions_verified",
                    "venue_directions_verified_at",
                    "venue_directions_verified_by",
                ),
                "description": (
                    "Only mark a destination verified after checking it with the "
                    "committee. No directions link is published otherwise."
                ),
            },
        ),
        ("General information", {"fields": ("general_information",)}),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    readonly_fields = (
        "allocation_strategy_approved_at",
        "allocation_strategy_approved_by",
        "allocation_strategy_approval_note",
        "allocation_approved_configuration",
        "venue_directions_verified_at",
        "venue_directions_verified_by",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("dic.can_verify_venue_directions"):
            fields.append("venue_directions_verified")
        if (
            obj
            and obj.year == 2026
            and not request.user.has_perm("dic.can_edit_confirmed_dic_details")
            and not request.user.is_superuser
        ):
            fields.extend(
                (
                    "year",
                    "camp_start_date",
                    "camp_end_date",
                    "venue_name",
                )
            )
        return fields

    @admin.display(description="Pricing configuration")
    def pricing_status(self, obj):
        return obj.pricing_configuration_status

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            previous = None
            if change:
                previous = CampEdition.objects.select_for_update().get(pk=obj.pk)
            confirmed_fields = ("year", "camp_start_date", "camp_end_date", "venue_name")
            confirmed_details_changed = previous and any(
                getattr(previous, field) != getattr(obj, field)
                for field in confirmed_fields
            )
            may_edit_confirmed_details = (
                request.user.is_superuser
                or request.user.has_perm("dic.can_edit_confirmed_dic_details")
            )
            if not change and obj.year == 2026:
                raise ValidationError(
                    "Create the confirmed DIC 2026 listing with the "
                    "setup_dic_2026 management command."
                )
            if (
                confirmed_details_changed
                and (previous.year == 2026 or obj.year == 2026)
                and not may_edit_confirmed_details
            ):
                raise PermissionDenied

            if change:
                previous_strategy = CampEdition.objects.filter(pk=obj.pk).values_list(
                    "allocation_strategy",
                    flat=True,
                ).first()
                if previous_strategy != obj.allocation_strategy:
                    obj.allocation_strategy_approved_at = None
                    obj.allocation_strategy_approved_by = None
                    obj.allocation_strategy_approval_note = ""
                    obj.allocation_approved_configuration = ""
                destination_fields = (
                    "venue_directions_address",
                    "venue_google_place_id",
                    "venue_latitude",
                    "venue_longitude",
                )
                destination_changed = previous and any(
                    getattr(previous, field) != getattr(obj, field)
                    for field in destination_fields
                )
                if destination_changed:
                    if (
                        obj.venue_directions_verified
                        and request.user.has_perm("dic.can_verify_venue_directions")
                    ):
                        obj.venue_directions_verified_at = timezone.now()
                        obj.venue_directions_verified_by = request.user
                    else:
                        obj.venue_directions_verified = False
                        obj.venue_directions_verified_at = None
                        obj.venue_directions_verified_by = None
            if (
                obj.venue_directions_verified
                and request.user.has_perm("dic.can_verify_venue_directions")
                and (
                    previous is None
                    or not previous.venue_directions_verified
                    or any(
                        getattr(previous, field) != getattr(obj, field)
                        for field in (
                            "venue_directions_address",
                            "venue_google_place_id",
                            "venue_latitude",
                            "venue_longitude",
                        )
                    )
                )
            ):
                obj.venue_directions_verified_at = timezone.now()
                obj.venue_directions_verified_by = request.user
            if obj.registration_status == CampEdition.RegistrationStatus.OPEN:
                errors = obj.pricing_configuration_errors()
                if errors:
                    raise ValidationError(errors)
            super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is not House:
            return super().save_formset(request, form, formset, change)
        with transaction.atomic():
            CampEdition.objects.select_for_update().get(pk=form.instance.pk)
            for inline_form in formset.forms:
                if inline_form.instance.pk and inline_form.has_changed():
                    previous_status = House.objects.filter(
                        pk=inline_form.instance.pk
                    ).values_list("status", flat=True).first()
                    if previous_status != inline_form.instance.status:
                        inline_form.instance.reserve_authorized_at = None
                        inline_form.instance.reserve_authorized_by = None
                        inline_form.instance.reserve_authorization_reason = ""
            super().save_formset(request, form, formset, change)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/allocation-console/",
                self.admin_site.admin_view(self.allocation_console),
                name="dic_campedition_allocation_console",
            ),
            path(
                "<path:object_id>/approve-allocation-strategy/",
                self.admin_site.admin_view(self.approve_allocation_strategy),
                name="dic_campedition_approve_allocation_strategy",
            ),
        ]
        return custom_urls + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["can_allocate"] = request.user.has_perm(
            "dic.can_allocate_participants"
        )
        extra_context["can_approve_allocation"] = request.user.has_perm(
            "dic.can_approve_allocation_strategy"
        )
        extra_context["allocation_console_url"] = reverse(
            "admin:dic_campedition_allocation_console",
            args=(object_id,),
        )
        extra_context["allocation_approval_url"] = reverse(
            "admin:dic_campedition_approve_allocation_strategy",
            args=(object_id,),
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def _require_allocation_permission(self, request, permission):
        if not request.user.has_perm(permission):
            raise PermissionDenied

    def allocation_console(self, request, object_id):
        self._require_allocation_permission(request, "dic.can_allocate_participants")
        edition = get_object_or_404(CampEdition, pk=unquote(object_id))
        houses = (
            House.objects.filter(edition=edition)
            .annotate(
                occupied_count=Count(
                    "allocations",
                    filter=Q(allocations__status=HouseAllocation.Status.ALLOCATED),
                )
            )
            .order_by("gender", "purpose", "name")
        )
        unallocated = unallocated_paid_participants(edition)
        if request.method == "POST":
            try:
                allocated = allocate_participants(
                    edition.pk,
                    request.POST.getlist("participant_ids"),
                    request.user,
                )
            except (AllocationError, ValueError) as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"Allocated {len(allocated)} paid participant(s).",
                    level=messages.SUCCESS,
                )
            return HttpResponseRedirect(request.path)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"House allocation — {edition}",
            "edition": edition,
            "houses": houses,
            "unallocated": unallocated.order_by("sex", "full_name", "pk"),
            "strategy_approved": (
                edition.allocation_strategy == CampEdition.AllocationStrategy.BALANCED
                and edition.allocation_strategy_approved_at is not None
                and edition.allocation_approved_configuration
                == allocation_configuration_fingerprint(edition)
            ),
        }
        return TemplateResponse(request, "admin/dic/allocation_console.html", context)

    @transaction.atomic
    def approve_allocation_strategy(self, request, object_id):
        self._require_allocation_permission(
            request,
            "dic.can_approve_allocation_strategy",
        )
        edition = get_object_or_404(CampEdition, pk=unquote(object_id))
        if request.method == "POST":
            edition = CampEdition.objects.select_for_update().get(pk=edition.pk)
            confirmation = request.POST.get("confirm") == "yes"
            note = request.POST.get("reason", "").strip()
            if not confirmation or not note:
                self.message_user(
                    request,
                    "Confirm approval and provide the committee approval reference or note.",
                    level=messages.ERROR,
                )
            elif edition.allocation_strategy != CampEdition.AllocationStrategy.BALANCED:
                self.message_user(
                    request,
                    "Select the balanced strategy on the edition before approving it.",
                    level=messages.ERROR,
                )
            else:
                edition.allocation_strategy_approved_at = timezone.now()
                edition.allocation_strategy_approved_by = request.user
                edition.allocation_strategy_approval_note = note
                edition.allocation_approved_configuration = (
                    allocation_configuration_fingerprint(edition)
                )
                edition.save(
                    update_fields=(
                        "allocation_strategy_approved_at",
                        "allocation_strategy_approved_by",
                        "allocation_strategy_approval_note",
                        "allocation_approved_configuration",
                    )
                )
                self.message_user(request, "Allocation strategy approved.", messages.SUCCESS)
                return HttpResponseRedirect(
                    reverse("admin:dic_campedition_change", args=(edition.pk,))
                )
        return TemplateResponse(
            request,
            "admin/dic/allocation_confirm.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Approve allocation strategy — {edition}",
                "object_label": str(edition),
                "action_label": "Approve allocation strategy",
                "needs_confirmation": True,
                "cancel_url": reverse("admin:dic_campedition_change", args=(edition.pk,)),
            },
        )


@admin.register(RegistrationCategory)
class RegistrationCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "edition",
        "minimum_age",
        "maximum_age",
        "early_bird_fee_ngn",
        "fee_ngn",
        "is_active",
    )
    list_filter = ("edition", "is_active")
    search_fields = ("name", "edition__name")
    autocomplete_fields = ("edition",)

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            CampEdition.objects.select_for_update().get(pk=obj.edition_id)
            super().save_model(request, obj, form, change)


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    change_form_template = "admin/dic/change_form.html"
    list_display = (
        "name",
        "edition",
        "gender",
        "purpose",
        "capacity",
        "status",
        "occupancy",
        "remaining_capacity",
        "reserve_authorized_at",
    )
    list_filter = ("edition", "gender", "purpose", "status", "reserve_authorized_at")
    search_fields = ("name", "edition__name")
    autocomplete_fields = ("edition",)
    readonly_fields = (
        "reserve_authorized_at",
        "reserve_authorized_by",
        "reserve_authorization_reason",
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            CampEdition.objects.select_for_update().get(pk=obj.edition_id)
            if change:
                previous_status = House.objects.filter(pk=obj.pk).values_list(
                    "status",
                    flat=True,
                ).first()
                if previous_status != obj.status:
                    obj.reserve_authorized_at = None
                    obj.reserve_authorized_by = None
                    obj.reserve_authorization_reason = ""
            super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            allocation_occupancy=Count(
                "allocations",
                filter=Q(allocations__status=HouseAllocation.Status.ALLOCATED),
            )
        )

    @admin.display(description="Occupancy", ordering="allocation_occupancy")
    def occupancy(self, obj):
        return obj.allocation_occupancy

    @admin.display(description="Remaining capacity")
    def remaining_capacity(self, obj):
        if obj.capacity is None:
            return "Unlimited"
        return max(obj.capacity - obj.allocation_occupancy, 0)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/reserve-authorization/",
                self.admin_site.admin_view(self.reserve_authorization),
                name="dic_house_reserve_authorization",
            ),
        ]
        return custom_urls + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["can_authorize_reserve"] = request.user.has_perm(
            "dic.can_activate_reserve_houses"
        )
        extra_context["reserve_authorization_url"] = reverse(
            "admin:dic_house_reserve_authorization",
            args=(object_id,),
        )
        return super().change_view(request, object_id, form_url, extra_context)

    @transaction.atomic
    def reserve_authorization(self, request, object_id):
        if not request.user.has_perm("dic.can_activate_reserve_houses"):
            raise PermissionDenied
        house = get_object_or_404(House, pk=unquote(object_id))
        if house.status != House.Status.RESERVE:
            self.message_user(
                request,
                "Only reserve houses can be authorized here.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse("admin:dic_house_change", args=(house.pk,)))
        if request.method == "POST":
            CampEdition.objects.select_for_update().get(pk=house.edition_id)
            house.refresh_from_db()
            if house.status != House.Status.RESERVE:
                raise PermissionDenied
            action = request.POST.get("action")
            reason = request.POST.get("reason", "").strip()
            if request.POST.get("confirm") != "yes" or not reason:
                self.message_user(
                    request,
                    "Confirm the action and provide an authorization reason.",
                    level=messages.ERROR,
                )
            elif action == "revoke" and house.allocations.filter(
                status=HouseAllocation.Status.ALLOCATED
            ).exists():
                self.message_user(
                    request,
                    "Release or reassign existing allocations before revoking reserve authorization.",
                    level=messages.ERROR,
                )
            elif action in ("authorize", "revoke"):
                house.reserve_authorized_at = timezone.now() if action == "authorize" else None
                house.reserve_authorized_by = request.user if action == "authorize" else None
                house.reserve_authorization_reason = reason
                house.save(
                    update_fields=(
                        "reserve_authorized_at",
                        "reserve_authorized_by",
                        "reserve_authorization_reason",
                    )
                )
                self.message_user(
                    request,
                    f"Reserve authorization {action}d.",
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(reverse("admin:dic_house_change", args=(house.pk,)))
        return TemplateResponse(
            request,
            "admin/dic/allocation_confirm.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Reserve-house authorization — {house}",
                "object_label": str(house),
                "action_label": (
                    "Authorize reserve house"
                    if not house.reserve_authorized_at
                    else "Revoke reserve authorization"
                ),
                "action_value": (
                    "authorize" if not house.reserve_authorized_at else "revoke"
                ),
                "needs_confirmation": True,
                "cancel_url": reverse("admin:dic_house_change", args=(house.pk,)),
            },
        )


@admin.register(PrimaryRegistrant)
class PrimaryRegistrantAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "created_at")
    search_fields = ("id", "full_name")
    readonly_fields = ("id", "created_at")
    fields = ("id", "full_name", "phone", "email", "created_at")


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "sex",
        "academic_status",
        "eligible_for_dedicated_accommodation",
        "allocation_overview",
        "created_at",
    )
    list_filter = ("sex", "academic_status", "occupation", "marital_status")
    search_fields = ("full_name", "email", "phone")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        "full_name",
        "address",
        "phone",
        "email",
        "date_of_birth",
        "sex",
        "height_cm",
        "weight_kg",
        "academic_status",
        "occupation",
        "marital_status",
        "eligible_for_dedicated_accommodation",
        "created_at",
        "updated_at",
    )
    inlines = (HouseAllocationInline,)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        permission = "dic.can_authorize_dedicated_accommodation"
        if not request.user.has_perm(permission):
            fields.append("eligible_for_dedicated_accommodation")
        return fields

    @admin.display(description="House allocations")
    def allocation_overview(self, obj):
        active = obj.house_allocations.filter(status=HouseAllocation.Status.ALLOCATED)
        return ", ".join(
            f"{allocation.edition.year}: {allocation.house.name}"
            for allocation in active.select_related("edition", "house")
        ) or "Unallocated"


@admin.register(RegistrationOrder)
class RegistrationOrderAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "edition",
        "status",
        "payment_status",
        "total_amount",
        "created_at",
    )
    list_filter = ("edition", "status", "payment_status", "created_at")
    search_fields = (
        "public_id",
        "primary_registrant__full_name",
        "items__participant__full_name",
    )
    readonly_fields = (
        "public_id",
        "primary_registrant",
        "edition",
        "payment_status",
        "total_amount",
        "access_token_expires_at",
        "access_token_revoked_at",
        "created_at",
        "submitted_at",
    )
    fields = (
        "public_id",
        "primary_registrant",
        "edition",
        "status",
        "payment_status",
        "total_amount",
        "access_token_expires_at",
        "access_token_revoked_at",
        "created_at",
        "submitted_at",
    )
    inlines = (RegistrationOrderItemInline, RegistrationOrderPriceRevisionInline)
    actions = ("revoke_order_access",)

    @admin.display(description="Total (NGN)")
    def total_amount(self, obj):
        return obj.total_amount_ngn

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Revoke selected order access tokens")
    def revoke_order_access(self, request, queryset):
        queryset.filter(access_token_revoked_at__isnull=True).update(
            access_token_revoked_at=timezone.now()
        )


@admin.register(RegistrationOrderItem)
class RegistrationOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "category_name_snapshot",
        "fee_snapshot_ngn",
        "created_at",
    )
    list_filter = ("category", "created_at")
    search_fields = ("order__public_id", "participant__full_name")
    readonly_fields = tuple(field.name for field in RegistrationOrderItem._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "order",
        "status",
        "amount_kobo",
        "currency",
        "provider_status",
        "provider_paid_at",
        "created_at",
        "verified_at",
    )
    list_filter = ("status", "currency", "created_at", "verified_at")
    search_fields = ("reference", "order__public_id", "provider_transaction_id")
    readonly_fields = tuple(
        field.name
        for field in PaymentAttempt._meta.fields
        if field.name != "authorization_url"
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegistrationOrderPriceItem)
class RegistrationOrderPriceItemAdmin(admin.ModelAdmin):
    list_display = (
        "revision",
        "category_name_snapshot",
        "price_type",
        "fee_snapshot_ngn",
    )
    list_filter = ("price_type",)
    search_fields = ("revision__order__public_id", "category_name_snapshot")
    readonly_fields = tuple(
        field.name for field in RegistrationOrderPriceItem._meta.fields
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaystackWebhookEvent)
class PaystackWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "reference",
        "processing_status",
        "payment_attempt",
        "created_at",
        "processed_at",
    )
    list_filter = ("event_type", "processing_status", "created_at")
    search_fields = ("reference", "payment_attempt__reference")
    readonly_fields = tuple(
        field.name
        for field in PaystackWebhookEvent._meta.fields
        if field.name != "payload_digest"
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HouseAllocation)
class HouseAllocationAdmin(admin.ModelAdmin):
    change_form_template = "admin/dic/change_form.html"
    form = HouseAllocationCreateForm
    list_display = (
        "participant",
        "edition",
        "house",
        "status",
        "allocated_at",
        "allocated_by",
        "source",
    )
    list_filter = ("edition", "house", "status", "source", "allocated_at")
    search_fields = ("participant__full_name", "house__name", "edition__name")
    autocomplete_fields = ("edition", "participant", "house")
    readonly_fields = (
        "status",
        "allocated_at",
        "allocated_by",
        "released_at",
        "released_by",
        "source",
        "previous_allocation",
        "resolution_reason",
    )
    fields = (
        "edition",
        "participant",
        "house",
        "status",
        "allocated_at",
        "allocated_by",
        "source",
        "previous_allocation",
        "change_reason",
        "resolution_reason",
        "released_at",
        "released_by",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.append("change_reason")
        return fields

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/release/",
                self.admin_site.admin_view(self.release_view),
                name="dic_houseallocation_release",
            ),
            path(
                "<path:object_id>/reassign/",
                self.admin_site.admin_view(self.reassign_view),
                name="dic_houseallocation_reassign",
            ),
        ]
        return custom_urls + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        allocation = get_object_or_404(HouseAllocation, pk=unquote(object_id))
        extra_context = extra_context or {}
        extra_context["can_release_allocation"] = request.user.has_perm(
            "dic.can_release_allocations"
        )
        extra_context["can_reassign_allocation"] = request.user.has_perm(
            "dic.can_reassign_allocations"
        )
        extra_context.update(
            {
                "release_allocation_url": reverse(
                    "admin:dic_houseallocation_release",
                    args=(allocation.pk,),
                ),
                "reassign_allocation_url": reverse(
                    "admin:dic_houseallocation_reassign",
                    args=(allocation.pk,),
                ),
                "allocation_is_active": (
                    allocation.status == HouseAllocation.Status.ALLOCATED
                ),
            }
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):
        return request.user.has_perm("dic.can_allocate_participants")

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or any(
            request.user.has_perm(f"dic.{permission}")
            for permission in (
                "can_allocate_participants",
                "can_reassign_allocations",
                "can_release_allocations",
            )
        )

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_change_permission(
            request,
            obj,
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            return
        allocation = assign_participant(
            obj.participant_id,
            obj.edition_id,
            obj.house_id,
            request.user,
            reason=obj.change_reason,
            source=HouseAllocation.Source.ADMIN,
        )
        obj.pk = allocation.pk

    def release_view(self, request, object_id):
        if not request.user.has_perm("dic.can_release_allocations"):
            raise PermissionDenied
        allocation = get_object_or_404(
            HouseAllocation.objects.select_related("participant", "house", "edition"),
            pk=unquote(object_id),
        )
        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()
            if request.POST.get("confirm") != "yes":
                self.message_user(request, "Confirm the release before continuing.", messages.ERROR)
            else:
                try:
                    release_allocation(allocation.pk, request.user, reason)
                except AllocationError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                else:
                    self.message_user(request, "Allocation released.", messages.SUCCESS)
                    return HttpResponseRedirect(
                        reverse("admin:dic_houseallocation_change", args=(allocation.pk,))
                    )
        return TemplateResponse(
            request,
            "admin/dic/allocation_confirm.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Release allocation — {allocation.participant}",
                "object_label": str(allocation),
                "action_label": "Release allocation",
                "action_value": "release",
                "needs_confirmation": True,
                "cancel_url": reverse(
                    "admin:dic_houseallocation_change",
                    args=(allocation.pk,),
                ),
            },
        )

    def reassign_view(self, request, object_id):
        if not request.user.has_perm("dic.can_reassign_allocations"):
            raise PermissionDenied
        allocation = get_object_or_404(
            HouseAllocation.objects.select_related("participant", "house", "edition"),
            pk=unquote(object_id),
        )
        houses = House.objects.filter(edition=allocation.edition).exclude(
            status=House.Status.INACTIVE
        )
        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()
            house_id = request.POST.get("house")
            if request.POST.get("confirm") != "yes":
                self.message_user(request, "Confirm the reassignment before continuing.", messages.ERROR)
            else:
                try:
                    if not house_id:
                        raise AllocationError("Select a house before confirming reassignment.")
                    assign_participant(
                        allocation.participant_id,
                        allocation.edition_id,
                        house_id,
                        request.user,
                        reason=reason,
                        source=HouseAllocation.Source.ADMIN,
                        reassign=True,
                    )
                except (AllocationError, ObjectDoesNotExist, ValueError, TypeError) as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                else:
                    self.message_user(
                        request,
                        "Allocation reassigned; the prior allocation remains in history.",
                        messages.SUCCESS,
                    )
                    return HttpResponseRedirect(
                        reverse("admin:dic_houseallocation_changelist")
                    )
        return TemplateResponse(
            request,
            "admin/dic/allocation_confirm.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Reassign — {allocation.participant}",
                "object_label": str(allocation),
                "action_label": "Reassign house",
                "action_value": "reassign",
                "houses": houses,
                "current_house_id": allocation.house_id,
                "needs_confirmation": True,
                "cancel_url": reverse(
                    "admin:dic_houseallocation_change",
                    args=(allocation.pk,),
                ),
            },
        )
