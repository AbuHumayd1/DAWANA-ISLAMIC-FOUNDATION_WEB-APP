from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from .allocation import AllocationError
from .housing_service import audit, review_guardian, permitted
from .housing_queue import retry
from .models import GuardianRelationship, HousingJob


class RetainedAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GuardianRelationship)
class GuardianRelationshipAdmin(RetainedAdmin):
    list_display = ('child', 'guardian', 'edition', 'status', 'reviewed_by', 'reviewed_at')
    list_filter = ('edition', 'status')
    search_fields = ('child__full_name', 'guardian__full_name')
    autocomplete_fields = ('child', 'guardian', 'edition')
    readonly_fields = ('status', 'approved_by', 'approved_at', 'reviewed_by', 'reviewed_at', 'created_at', 'supervisor_review')

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj:
            fields += ['edition', 'child', 'guardian', 'reason']
        return fields

    def has_add_permission(self, request):
        return request.user.has_perm('dic.can_approve_housing_guardians')

    def has_change_permission(self, request, obj=None):
        return request.method in ('GET', 'HEAD') and (super().has_change_permission(request, obj) or self.has_add_permission(request))

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or self.has_add_permission(request)

    def save_model(self, request, obj, form, change):
        permitted(request.user, 'can_approve_housing_guardians')
        obj.save()
        audit(request.user, 'housing_guardian_requested', obj,
              {'child_id': str(obj.child_id), 'guardian_id': str(obj.guardian_id), 'reason': obj.reason})

    @admin.display(description='Supervisor decision')
    def supervisor_review(self, obj):
        if not obj or not obj.pk:
            return 'Save the pending relationship, then open supervisor review.'
        return format_html('<a href="{}">Review guardian approval / rejection / revocation</a>', reverse('admin:dic_guardian_review', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:pk>/review/', self.admin_site.admin_view(self.review), name='dic_guardian_review')] + super().get_urls()

    def review(self, request, pk):
        permitted(request.user, 'can_approve_housing_guardians')
        obj = get_object_or_404(GuardianRelationship, pk=pk)
        if request.method == 'POST':
            try:
                if request.POST.get('confirm') != 'yes':
                    raise AllocationError('Confirm the supervisor decision.')
                review_guardian(pk, request.user, request.POST.get('decision'), request.POST.get('reason', ''))
            except AllocationError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.message_user(request, 'Guardian decision recorded with audit history.', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:dic_guardianrelationship_change', args=[pk]))
        return TemplateResponse(request, 'admin/dic/housing_review.html', {
            **self.admin_site.each_context(request), 'title': 'Guardian supervisor review', 'object': obj,
            'decisions': [('approved', 'Approve'), ('rejected', 'Reject')] if obj.status == 'pending' else [('revoked', 'Revoke')] if obj.status == 'approved' else [],
            'opts': self.model._meta,
        })


@admin.register(HousingJob)
class HousingJobAdmin(RetainedAdmin):
    list_display = ('participant', 'edition', 'state', 'attempts', 'reason', 'updated_at')
    list_filter = ('edition', 'state')
    search_fields = ('participant__full_name', 'reason')
    readonly_fields = tuple(field.name for field in HousingJob._meta.fields) + ('supervisor_retry',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ('GET', 'HEAD') and super().has_change_permission(request, obj)

    @admin.display(description='Explicit retry')
    def supervisor_retry(self, obj):
        return format_html('<a href="{}">Retry held / failed job with reason</a>', reverse('admin:dic_housing_retry', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:pk>/retry/', self.admin_site.admin_view(self.retry_view), name='dic_housing_retry')] + super().get_urls()

    def retry_view(self, request, pk):
        permitted(request.user, 'can_process_housing_queue')
        obj = get_object_or_404(HousingJob, pk=pk)
        if request.method == 'POST':
            try:
                if request.POST.get('confirm') != 'yes':
                    raise AllocationError('Confirm the explicit retry.')
                retry(pk, request.user, request.POST.get('reason', ''))
            except AllocationError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.message_user(request, 'Retry queued. Run the bounded worker when ready.', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:dic_housingjob_change', args=[pk]))
        return TemplateResponse(request, 'admin/dic/housing_review.html', {
            **self.admin_site.each_context(request), 'title': 'Explicit housing retry', 'object': obj,
            'opts': self.model._meta, 'retry_only': True,
        })
