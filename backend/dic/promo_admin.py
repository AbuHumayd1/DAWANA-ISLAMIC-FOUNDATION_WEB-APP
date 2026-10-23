from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from .models import CampEdition, DICAdminAuditEvent
from .promo_models import PromoVideo, CampFlyer
from .memory_storage import private_memory_storage


class EditorialAssetForm(forms.ModelForm):
    class Meta:
        fields = '__all__'
        widgets = {name: forms.FileInput() for name in ('video', 'poster', 'image')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['state'].choices = [('draft', 'Draft'), ('review', 'Ready for review')]
        if self.instance.state == 'published':
            self.initial['state'] = 'review'

    def clean(self):
        cleaned = super().clean()
        for name in ('video', 'poster', 'image'):
            value = cleaned.get(name)
            if value and not getattr(value, '_committed', False):
                try:
                    private_memory_storage._backend()
                except ImproperlyConfigured:
                    self.add_error(name, 'Configure private DIC storage before uploading.')
        return cleaned


class AssetAdmin(admin.ModelAdmin):
    form = EditorialAssetForm
    list_display = ('title', 'edition', 'state', 'display_order', 'published_at')
    list_filter = ('edition', 'state')
    readonly_fields = ('published_by', 'published_at', 'private_preview')
    actions = ('publish_selected', 'withdraw_selected')

    def has_delete_permission(self, request, obj=None):
        return False  # Retention/cleanup needs a separate decision.

    def has_publish_permission(self, request):
        return self.has_change_permission(request) and request.user.has_perm(f'dic.publish_{self.model._meta.model_name}')

    @admin.display(description='Private preview')
    def private_preview(self, obj):
        if not obj.pk:
            return 'Save a draft to preview.'
        route = 'promo-stream' if isinstance(obj, PromoVideo) else 'official-flyer'
        return format_html('<a href="{}?preview=1" target="_blank" rel="noopener">Preview asset</a>', reverse(f'dic:{route}', args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        obj.save(actor=request.user)
        DICAdminAuditEvent.objects.create(actor=request.user, action='dic_asset_edited', target_type=obj._meta.object_name, target_id=str(obj.pk), details={})

    @admin.action(description='Approve and publish selected assets', permissions=['publish'])
    def publish_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        for selected in queryset:
            try:
                with transaction.atomic():
                    obj = self.model.objects.select_for_update().get(pk=selected.pk)
                    # Lock before constraint validation: concurrent flyer publication
                    # should return an admin validation error, not an integrity error.
                    CampEdition.objects.select_for_update().get(pk=obj.edition_id)
                    obj.state = 'published'
                    obj.full_clean()
                    obj.save(actor=request.user)
                    DICAdminAuditEvent.objects.create(actor=request.user, action='dic_asset_published', target_type=obj._meta.object_name, target_id=str(obj.pk), details={})
            except ValidationError as error:
                self.message_user(request, '; '.join(error.messages), level=messages.ERROR)

    @admin.action(description='Withdraw selected assets', permissions=['publish'])
    def withdraw_selected(self, request, queryset):
        if not self.has_publish_permission(request):
            raise PermissionDenied
        with transaction.atomic():
            for obj in queryset.select_for_update():
                queryset.filter(pk=obj.pk).update(state='draft', published_at=None, published_by=None, updated_at=timezone.now())
                DICAdminAuditEvent.objects.create(actor=request.user, action='dic_asset_withdrawn', target_type=obj._meta.object_name, target_id=str(obj.pk), details={})


@admin.register(PromoVideo)
class PromoVideoAdmin(AssetAdmin):
    list_filter = ('edition', 'kind', 'state')
    list_display = ('title', 'edition', 'kind', 'state', 'display_order', 'published_at')


@admin.register(CampFlyer)
class CampFlyerAdmin(AssetAdmin):
    pass
