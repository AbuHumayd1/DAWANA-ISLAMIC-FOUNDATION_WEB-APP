from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from .memory_models import CampPhotograph, MemoryActivity
from .memory_storage import private_memory_storage
from .models import DICAdminAuditEvent


class PhotographForm(forms.ModelForm):
    class Meta:
        model = CampPhotograph
        exclude = ("published_at", "published_by")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = [("draft", "Draft"), ("review", "Ready for review")]
        if self.instance.pk and self.instance.state == "published":
            self.initial["state"] = "review"
        self.fields["photograph"].widget = forms.FileInput()

    def clean_photograph(self):
        photo = self.cleaned_data.get("photograph")
        if photo and not getattr(photo, "_committed", False):
            try:
                private_memory_storage._backend()
            except ImproperlyConfigured:
                raise forms.ValidationError("Uploads are disabled until private photo storage is configured and verified.") from None
        return photo


@admin.register(MemoryActivity)
class MemoryActivityAdmin(admin.ModelAdmin):
    search_fields = ("name",)

    def has_delete_permission(self, request, obj=None):
        # Keep published categorization stable; unused tags can be retained.
        return False

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change and form.changed_data:
                for photo in obj.campphotograph_set.select_for_update().filter(state="published"):
                    photo.state = "review"
                    photo.save(actor=request.user)
            super().save_model(request, obj, form, change)


@admin.register(CampPhotograph)
class CampPhotographAdmin(admin.ModelAdmin):
    form = PhotographForm
    list_display = ("caption", "edition", "state", "featured", "display_order", "published_by", "published_at")
    list_filter = ("state", "edition", "activities", "featured")
    search_fields = ("caption", "alt_text")
    filter_horizontal = ("activities",)
    readonly_fields = ("published_by", "published_at", "private_preview")
    actions = ("publish_selected", "unpublish_selected")

    @admin.display(description="Private preview")
    def private_preview(self, obj):
        if not obj.pk:
            return "Save a draft to preview."
        return format_html('<a href="{}?preview=1" target="_blank" rel="noopener">View photograph</a>', reverse("dic:memory-image", args=[obj.pk]))

    def has_publish_permission(self, request):
        return self.has_change_permission(request) and request.user.has_perm("dic.publish_campphotograph")

    def save_model(self, request, obj, form, change):
        if not self.has_change_permission(request, obj) and change:
            raise PermissionDenied
        # Every content edit withdraws publication until a publisher approves it again.
        obj.save(actor=request.user)

    @admin.action(description="Approve and publish selected photographs", permissions=["publish"])
    def publish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for photo in queryset.select_for_update().prefetch_related("activities"):
                photo.full_clean()
                photo.state = "published"
                photo.save(actor=request.user)
                DICAdminAuditEvent.objects.create(actor=request.user, action="camp_photo_published", target_type="CampPhotograph", target_id=str(photo.pk), details={})

    @admin.action(description="Withdraw selected photographs", permissions=["publish"])
    def unpublish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for photo in queryset.select_for_update():
                photo.state = "draft"
                photo.save(actor=request.user)
                DICAdminAuditEvent.objects.create(actor=request.user, action="camp_photo_withdrawn", target_type="CampPhotograph", target_id=str(photo.pk), details={})
