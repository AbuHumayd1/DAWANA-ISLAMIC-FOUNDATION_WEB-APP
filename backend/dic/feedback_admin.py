"""Only explicit lecturer/account mapping is exposed in Admin; no response browser."""
from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import LecturerFeedbackAccess, LecturerAppearance, DICAdminAuditEvent


@admin.register(LecturerFeedbackAccess)
class LecturerFeedbackAccessAdmin(admin.ModelAdmin):
    list_display=('edition','lecturer','user','enabled')
    list_filter=('edition','enabled')

    def permitted(self,request):
        return request.user.is_active and request.user.is_staff and request.user.has_perm('dic.can_configure_dic_feedback')

    def has_module_permission(self,request): return self.permitted(request)
    def has_view_permission(self,request,obj=None): return self.permitted(request)
    def has_add_permission(self,request): return self.permitted(request)
    def has_change_permission(self,request,obj=None): return self.permitted(request)
    def has_delete_permission(self,request,obj=None): return False

    def get_form(self,request,obj=None,**kwargs):
        base=super().get_form(request,obj,**kwargs)
        class AccessForm(base):
            def clean(self):
                data=super().clean(); user=data.get('user'); lecturer=data.get('lecturer'); edition=data.get('edition')
                if user and not (user.is_active and user.is_staff and user.has_perm('dic.can_view_dic_operations') and user.has_perm('dic.can_submit_dic_lecturer_feedback')):
                    raise ValidationError('Choose an existing active staff account explicitly authorised for Operations and lecturer feedback.')
                if lecturer and edition:
                    appearance=LecturerAppearance.objects.filter(lecturer=lecturer,edition=edition).first()
                    if not appearance or not appearance.verified:
                        raise ValidationError('Lecturer must have verified participation with recorded evidence in this edition.')
                return data
        return AccessForm

    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        DICAdminAuditEvent.objects.create(actor=request.user,action='lecturer_feedback_access_configured',
            target_type='LecturerFeedbackAccess',target_id=str(obj.pk),details={'edition':obj.edition_id})
