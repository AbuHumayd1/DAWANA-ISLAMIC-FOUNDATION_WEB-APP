from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import User
from .participant_admin import ParticipantAwarePasswordChangeForm, participant_identity


class ParticipantAwareUserAdmin(UserAdmin):
    change_list_template = "admin/accounts/user/change_list.html"

    def get_urls(self):
        custom = [
            path(
                "provision-dawana-staff/",
                self.admin_site.admin_view(self.provision_dawana_staff),
                name="accounts_user_provision_dawana_staff",
            ),
        ]
        return custom + super().get_urls()

    def provision_dawana_staff(self, request):
        # Admin site enforces login and CSRF. Provisioning is owner-superuser-only.
        if not (request.user.is_authenticated and request.user.is_active
                and request.user.is_staff and request.user.is_superuser):
            raise PermissionDenied("Only an active owner superuser can prepare staff accounts.")

        from dic.management.commands.provision_dawana_staff_accounts import ACCOUNTS
        context = {
            **self.admin_site.each_context(request),
            "title": "Provision DAWANA staff accounts",
            "opts": self.model._meta,
            "accounts": ACCOUNTS,
            "confirmation": "PROVISION 8 STAFF ACCOUNTS",
        }
        if request.method == "POST":
            if request.POST.get("confirmation") != context["confirmation"]:
                self.message_user(request, "Confirmation phrase did not match. No accounts created.", level="error")
            else:
                try:
                    call_command(
                        "provision_dawana_staff_accounts",
                        apply=True,
                        approved_by=request.user.get_username(),
                    )
                except (CommandError, ValidationError) as exc:
                    # Provisioning runs transactionally; account collisions fail closed.
                    self.message_user(request, str(exc), level="error")
                else:
                    self.message_user(
                        request,
                        "Eight inactive staff accounts prepared. Privately assign unique passwords, "
                        "verify recipients, then enable each account individually.",
                        level="success",
                    )
                    return HttpResponseRedirect(reverse("admin:accounts_user_changelist"))
        return TemplateResponse(request, "admin/accounts/user/provision_staff.html", context)

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
