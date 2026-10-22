from django import forms
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone

from .memory_models import CampVideo
from .memory_storage import private_memory_storage
from .models import DICAdminAuditEvent


class VideoForm(forms.ModelForm):
    class Meta:
        model = CampVideo
        exclude = ("published_by", "published_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = [("draft", "Draft"), ("review", "Ready for review")]
        if self.instance.pk and self.instance.state == "published":
            self.initial["state"] = "review"
        self.fields["thumbnail"].widget = forms.FileInput()

    def clean_thumbnail(self):
        thumbnail = self.cleaned_data.get("thumbnail")
        if thumbnail and not getattr(thumbnail, "_committed", False):
            try:
                private_memory_storage._backend()
            except ImproperlyConfigured:
                raise forms.ValidationError("Configure and verify private thumbnail storage before uploading.") from None
        return thumbnail


@admin.register(CampVideo)
class CampVideoAdmin(admin.ModelAdmin):
    form = VideoForm
    list_display = ("caption", "edition", "state", "featured", "display_order", "published_by", "published_at")
    list_filter = ("edition", "state", "activities", "featured")
    search_fields = ("caption", "alt_text")
    filter_horizontal = ("activities",)
    readonly_fields = ("published_by", "published_at", "private_thumbnail")
    actions = ("publish_selected", "unpublish_selected")

    @admin.display(description="Private thumbnail preview")
    def private_thumbnail(self, obj):
        if not obj.pk:
            return "Save a draft to preview."
        return format_html('<a href="{}?preview=1" target="_blank" rel="noopener">View thumbnail</a>', reverse("dic:video-thumbnail", args=[obj.pk]))

    def has_publish_permission(self, request):
        return self.has_change_permission(request) and request.user.has_perm("dic.publish_campvideo")

    def save_model(self, request, obj, form, change):
        if change and not self.has_change_permission(request, obj):
            raise PermissionDenied
        obj.save(actor=request.user)

    @admin.action(description="Approve and publish selected videos", permissions=["publish"])
    def publish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for video in queryset.select_for_update():
                video.full_clean()
                video.state = "published"
                video.save(actor=request.user)
                DICAdminAuditEvent.objects.create(actor=request.user, action="camp_video_published", target_type="CampVideo", target_id=str(video.pk), details={})

    @admin.action(description="Withdraw selected videos", permissions=["publish"])
    def unpublish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for video in queryset.select_for_update():
                video.state = "draft"
                # Withdrawal must work even when the provider has been revoked.
                CampVideo.objects.filter(pk=video.pk).update(state="draft", published_at=None, published_by=None, updated_at=timezone.now())
                DICAdminAuditEvent.objects.create(actor=request.user, action="camp_video_withdrawn", target_type="CampVideo", target_id=str(video.pk), details={})
