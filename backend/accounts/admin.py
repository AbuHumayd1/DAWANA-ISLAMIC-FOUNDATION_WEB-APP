from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User
from .participant_admin import ParticipantAwarePasswordChangeForm, participant_identity


class ParticipantAwareUserAdmin(UserAdmin):
    def save_model(self, request, obj, form, change):
        # User management can confer staff/superuser access: reserve it for owners.
        if not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Owner administrator authority is required to manage staff accounts.')
        super().save_model(request,obj,form,change)

    def save_related(self,request,form,formsets,change):
        super().save_related(request,form,formsets,change)
        from dic.models import DICAdminAuditEvent
        user=form.instance
        DICAdminAuditEvent.objects.create(actor=request.user,action='staff_account_permissions_saved',
            target_type='User',target_id=str(user.pk),details={'active':user.is_active,'staff':user.is_staff,
            'superuser':user.is_superuser,'groups':list(user.groups.values_list('name',flat=True)),
            'permissions':list(user.user_permissions.values_list('codename',flat=True))})

    change_password_form = ParticipantAwarePasswordChangeForm

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        # Portal identifiers must change together with their canonical key via
        # the existing staff-reviewed credential transition, never one side only.
        return (*fields, 'username') if obj and participant_identity(obj) else fields


admin.site.register(User, ParticipantAwareUserAdmin)


from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
admin.site.unregister(Group)

@admin.register(Group)
class AuditedCommitteeGroupAdmin(GroupAdmin):
    def has_change_permission(self,request,obj=None):return request.user.is_superuser
    def has_add_permission(self,request):return request.user.is_superuser
    def has_delete_permission(self,request,obj=None):return request.user.is_superuser
    def save_related(self,request,form,formsets,change):
        super().save_related(request,form,formsets,change)
        from dic.models import DICAdminAuditEvent
        DICAdminAuditEvent.objects.create(actor=request.user,action='staff_group_permissions_saved',target_type='Group',
            target_id=str(form.instance.pk),details={'name':form.instance.name,
            'permissions':list(form.instance.permissions.values_list('codename',flat=True))})
