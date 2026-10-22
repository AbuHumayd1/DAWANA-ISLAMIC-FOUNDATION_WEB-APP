from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from .memory_storage import private_memory_storage
from .models import DICAdminAuditEvent
from .showcase_models import Lecturer, LecturerAppearance, CampActivity


def audit(request, obj, action):
    DICAdminAuditEvent.objects.create(actor=request.user, action=action, target_type=obj._meta.object_name, target_id=str(obj.pk), details={})


class ShowcaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "state" in self.fields:
            self.fields["state"].choices = [("draft", "Draft"), ("review", "Ready for review")]
            if self.instance.pk and self.instance.state == "published":
                self.initial["state"] = "review"
        if "confirmation_status" in self.fields:
            self.fields["confirmation_status"].choices = [("pending", "Pending"), ("invited", "Invited"), ("declined", "Declined")]
            if self.instance.pk and self.instance.confirmation_status == "confirmed":
                self.initial["confirmation_status"] = "pending"
        if "photograph" in self.fields:
            self.fields["photograph"].widget = forms.FileInput()

    def clean(self):
        cleaned = super().clean()
        photo = cleaned.get("photograph")
        if photo and not getattr(photo, "_committed", False):
            try:
                private_memory_storage._backend()
            except ImproperlyConfigured:
                self.add_error("photograph", "Configure and verify private image storage before uploading.")
        return cleaned


class EditorialAdmin(admin.ModelAdmin):
    form = ShowcaseForm
    list_display = ("__str__", "edition", "state", "featured", "display_order", "published_by", "published_at")
    list_filter = ("state", "edition", "featured")
    readonly_fields = ("published_by", "published_at", "private_preview")
    actions = ("publish_selected", "withdraw_selected")

    def has_publish_permission(self, request):
        return self.has_change_permission(request) and request.user.has_perm(f"dic.publish_{self.model._meta.model_name}")

    @admin.display(description="Private image preview")
    def private_preview(self, obj):
        if not obj.pk:
            return "Save a draft to preview."
        kind = "lecturer" if isinstance(obj, LecturerAppearance) else "activity"
        if kind == "activity" and not obj.photograph:
            return "No image."
        return format_html('<a href="{}?preview=1" target="_blank" rel="noopener">Private preview</a>', reverse("dic:showcase-image", args=[kind, obj.pk]))

    def save_model(self, request, obj, form, change):
        if (change and not self.has_change_permission(request, obj)) or (not change and not self.has_add_permission(request)):
            raise PermissionDenied
        obj.save(actor=request.user)
        audit(request, obj, "showcase_edited" if change else "showcase_created")

    def locked(self, queryset):
        if self.model is LecturerAppearance:
            ids = list(queryset.values_list("lecturer_id", flat=True))
            list(Lecturer.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        return queryset.select_for_update().order_by("pk")

    @admin.action(description="Approve and publish selected content", permissions=["publish"])
    def publish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        try:
            with transaction.atomic():
                for obj in self.locked(queryset):
                    obj.state = "published"
                    obj.full_clean()
                    obj.save(actor=request.user)
                    audit(request, obj, "showcase_published")
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), level=messages.ERROR)

    @admin.action(description="Withdraw selected content", permissions=["publish"])
    def withdraw_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for obj in self.locked(queryset):
                obj.state = "review"
                obj.save(actor=request.user)
                audit(request, obj, "showcase_withdrawn")


@admin.register(Lecturer)
class LecturerAdmin(admin.ModelAdmin):
    form = ShowcaseForm
    list_display = ("name", "designation")
    search_fields = ("name", "designation")
    readonly_fields = ("private_preview",)

    @admin.display(description="Private photograph")
    def private_preview(self, obj):
        if not obj.pk:
            return "Save to preview."
        return format_html('<a href="{}" target="_blank" rel="noopener">Private preview</a>', reverse("dic:showcase-image", args=["identity", obj.pk]))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit(request, obj, "lecturer_identity_edited" if change else "lecturer_identity_created")


@admin.register(LecturerAppearance)
class LecturerAppearanceAdmin(EditorialAdmin):
    search_fields = ("lecturer__name", "topic")
    list_filter = EditorialAdmin.list_filter + ("participation_type", "confirmation_status")
    readonly_fields = EditorialAdmin.readonly_fields + ("verified_by", "verified_at")
    actions = EditorialAdmin.actions + ("verify_selected",)

    def has_verify_permission(self, request):
        return self.has_change_permission(request) and request.user.has_perm("dic.verify_lecturerappearance")

    @admin.action(description="Verify participation and lecture topic using recorded evidence", permissions=["verify"])
    def verify_selected(self, request, queryset):
        if not self.has_verify_permission(request):
            raise PermissionDenied
        if queryset.exclude(verification_note="").count() != queryset.count() or any(not note.strip() for note in queryset.values_list("verification_note", flat=True)):
            self.message_user(request, "Save verification evidence for every selected appearance first.", level=messages.ERROR)
            return
        with transaction.atomic():
            for obj in self.locked(queryset):
                # Verification never publishes content. Any previous publication is withdrawn.
                obj.state = "review"
                obj.confirmation_status = "confirmed"
                obj.save(actor=request.user)
                audit(request, obj, "lecturer_participation_verified")


@admin.register(CampActivity)
class CampActivityAdmin(EditorialAdmin):
    search_fields = ("title", "description", "category")
    list_filter = EditorialAdmin.list_filter + ("category",)
