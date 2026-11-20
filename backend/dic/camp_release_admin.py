"""Existing Django Admin is the single content management interface."""
from django.contrib import admin,messages
from django import forms
from django.db import models
from django.urls import path,reverse
from django.utils.html import format_html,format_html_join
from django.http import FileResponse
from .media_delivery import safe_media
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from django.db import transaction
from .models import LectureRecording,CertificateRelease,ParticipationCertificate,DICAdminAuditEvent


def audit(actor,action,obj):
    DICAdminAuditEvent.objects.create(actor=actor,action=action,target_type=type(obj).__name__,target_id=str(obj.pk),details={})



class RecordingForm(forms.ModelForm):
    class Meta:
        model=LectureRecording
        exclude=('state','published_at','published_by')
        widgets={'audio':forms.FileInput()}
    def clean_audio(self):
        upload=self.cleaned_data.get('audio')
        if upload and not getattr(upload,'_committed',False):
            from .recording_storage import recording_storage
            from django.core.exceptions import ImproperlyConfigured
            try:recording_storage._backend()
            except ImproperlyConfigured:raise forms.ValidationError('Media uploads await owner-approved private storage activation.') from None
        return upload

@admin.register(LectureRecording)
class RecordingAdmin(admin.ModelAdmin):
    form=RecordingForm
    list_display=['title','edition','lecturer','state','published_at']
    list_filter=['edition','state'];search_fields=['title','lecturer','description']
    formfield_overrides={models.FileField:{'widget':forms.FileInput}}
    readonly_fields=['state','published_at','published_by','updated_at','preview']
    def get_urls(self):
        return [path('<int:pk>/listen/',self.admin_site.admin_view(self.listen),name='dic_recording_listen')]+super().get_urls()
    @admin.display(description='Private staff preview')
    def preview(self,obj):
        if not obj.pk:return 'Save a draft to preview.'
        return format_html('<a href="{}" target="_blank" rel="noopener">Listen to private draft</a>',reverse('admin:dic_recording_listen',args=[obj.pk]))
    @safe_media
    def listen(self,request,pk):
        obj=self.get_object(request,pk)
        if not obj or not self.has_view_permission(request,obj):raise PermissionDenied
        from pathlib import Path
        mime={'.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav','.ogg':'audio/ogg'}.get(Path(obj.audio.name).suffix.lower(),'application/octet-stream')
        response=FileResponse(obj.audio.open('rb'),content_type=mime)
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        return response
    actions=['publish','withdraw']
    def save_model(self,request,obj,form,change):
        obj.state='draft';obj.save(actor=request.user);audit(request.user,'recording_draft_saved',obj)
    def has_publish_permission(self,request):return request.user.has_perm('dic.publish_lecturerecording') and self.has_change_permission(request)
    @admin.action(description='Publish approved recordings',permissions=['publish'])
    def publish(self,request,queryset):
        if not self.has_publish_permission(request):raise PermissionDenied
        for row in queryset:
            row.full_clean();row.state='published';row.save(actor=request.user);audit(request.user,'recording_published',row)
    @admin.action(description='Withdraw recordings',permissions=['publish'])
    def withdraw(self,request,queryset):
        if not self.has_publish_permission(request):raise PermissionDenied
        for row in queryset:
            row.state='draft';row.save(actor=request.user);audit(request.user,'recording_withdrawn',row)
    def has_delete_permission(self,request,obj=None):return False


@admin.register(CertificateRelease)
class ReleaseAdmin(admin.ModelAdmin):
    list_display=['edition','enabled','release_at','artwork','release_readiness'];list_filter=['enabled']
    readonly_fields=['release_readiness']
    @admin.display(description='Certificate release readiness')
    def release_readiness(self,obj):
        if not obj or not obj.pk or not obj.edition_id:
            return 'Choose the camp edition and save a disabled draft first.'
        from .certificates import certificate_readiness
        problems=certificate_readiness(obj)
        if not problems:
            return 'Ready: the approved configuration is complete.'
        return format_html('<ul>{}</ul>',format_html_join('', '<li>{}</li>', ((p,) for p in problems)))

    def has_view_permission(self,request,obj=None):return request.user.has_perm('dic.release_dic_certificates')
    def has_add_permission(self,request):return self.has_view_permission(request)
    def has_change_permission(self,request,obj=None):return self.has_view_permission(request)
    def has_delete_permission(self,request,obj=None):return False
    def save_model(self,request,obj,form,change):
        if not self.has_change_permission(request,obj):raise PermissionDenied
        if obj.enabled:
            from .certificates import approved_artwork
            approved_artwork(obj)
        super().save_model(request,obj,form,change);audit(request.user,'certificate_release_updated',obj)


@admin.register(ParticipationCertificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display=['reference','participant_name','edition','revision','issued_at','revoked_at']
    list_filter=['edition','revoked_at'];search_fields=['participant_name','reference']
    readonly_fields=['reference','edition','participant','participant_name','revision','issued_at','revoked_at']
    actions=['revoke','reissue']
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False
    def has_change_permission(self,request,obj=None):return request.user.has_perm('dic.manage_dic_certificates')
    @admin.action(description='Revoke selected certificates')
    def revoke(self,request,queryset):
        if not self.has_change_permission(request):raise PermissionDenied
        for row in queryset:
            row.revoked_at=timezone.now();row.save(update_fields=['revoked_at']);audit(request.user,'certificate_revoked',row)
    @admin.action(description='Reissue with current authoritative name; retain reference')
    def reissue(self,request,queryset):
        if not self.has_change_permission(request):raise PermissionDenied
        with transaction.atomic():
            for row in queryset.select_for_update().select_related('participant'):
                row.revoked_at=None;row.participant_name=row.participant.full_name;row.revision+=1
                row.save(update_fields=['revoked_at','participant_name','revision']);audit(request.user,'certificate_reissued',row)
