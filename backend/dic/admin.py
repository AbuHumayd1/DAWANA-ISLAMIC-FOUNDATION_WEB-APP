from django.contrib import admin

from .models import (
    CampEdition,
    House,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)


class RegistrationCategoryInline(admin.TabularInline):
    model = RegistrationCategory
    extra = 0
    show_change_link = True
    fields = ("name", "minimum_age", "maximum_age", "fee_ngn", "is_active")


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


@admin.register(CampEdition)
class CampEditionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "year",
        "camp_start_date",
        "camp_end_date",
        "registration_status",
        "is_active",
    )
    list_filter = ("registration_status", "is_active", "year")
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
                )
            },
        ),
        ("General information", {"fields": ("general_information",)}),
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegistrationCategory)
class RegistrationCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "edition",
        "minimum_age",
        "maximum_age",
        "fee_ngn",
        "is_active",
    )
    list_filter = ("edition", "is_active")
    search_fields = ("name", "edition__name")
    autocomplete_fields = ("edition",)


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "edition",
        "gender",
        "purpose",
        "capacity",
        "status",
    )
    list_filter = ("edition", "gender", "purpose", "status")
    search_fields = ("name", "edition__name")
    autocomplete_fields = ("edition",)


@admin.register(PrimaryRegistrant)
class PrimaryRegistrantAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "created_at")
    search_fields = ("id", "full_name")
    readonly_fields = ("id", "created_at")
    fields = ("id", "full_name", "phone", "email", "created_at")


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "sex", "academic_status", "created_at")
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
        "created_at",
        "updated_at",
    )


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
        "idempotency_key_digest",
        "request_fingerprint",
        "access_token_digest",
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
        "idempotency_key_digest",
        "request_fingerprint",
        "access_token_digest",
        "created_at",
        "submitted_at",
    )
    inlines = (RegistrationOrderItemInline,)

    @admin.display(description="Total (NGN)")
    def total_amount(self, obj):
        return obj.total_amount_ngn

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
