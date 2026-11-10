from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import AcademicClass, AcademicAssignment, CampAnnouncement
from .launch_management import save_academic, save_announcement_draft, publish_announcement


def permitted(request, permission):
    return request.user.is_active and request.user.is_staff and request.user.has_perm('dic.' + permission)


class AcademicAdmin(admin.ModelAdmin):
    readonly_fields = ('modified_by', 'updated_at')
    list_filter = ('edition',)
    def has_module_permission(self, request): return self.has_view_permission(request)
    def has_view_permission(self, request, obj=None): return permitted(request,'manage_dic_classes')
    def has_add_permission(self, request): return permitted(request,'manage_dic_classes')
    def has_change_permission(self, request, obj=None): return permitted(request,'manage_dic_classes')
    def has_delete_permission(self, request, obj=None): return False
    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not self.has_change_permission(request,obj): raise PermissionDenied
        save_academic(obj, request.user)


@admin.register(AcademicClass)
class ClassAdmin(AcademicAdmin):
    list_display=('edition','name','active','modified_by','updated_at')


@admin.register(AcademicAssignment)
class AssignmentAdmin(AcademicAdmin):
    list_display=('edition','participant','academic_class','modified_by','updated_at')
    search_fields=('participant__full_name','academic_class__name')


@admin.register(CampAnnouncement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display=('title','edition','status','starts_at','ends_at','modified_by')
    list_filter=('edition','status')
    readonly_fields=('status','published_by','modified_by','created_at','updated_at')
    actions=('publish','unpublish')
    def has_module_permission(self,request): return self.has_view_permission(request)
    def has_view_permission(self,request,obj=None): return permitted(request,'manage_dic_announcements') or permitted(request,'publish_dic_announcements')
    def has_add_permission(self,request): return permitted(request,'manage_dic_announcements')
    def has_change_permission(self,request,obj=None): return permitted(request,'manage_dic_announcements') and (obj is None or obj.status=='draft')
    def has_delete_permission(self,request,obj=None): return False
    def get_readonly_fields(self,request,obj=None): return self.readonly_fields + (('edition',) if obj else ())
    def get_actions(self,request):
        actions=super().get_actions(request)
        if not permitted(request,'publish_dic_announcements'):
            actions.pop('publish',None); actions.pop('unpublish',None)
        return actions
    @transaction.atomic
    def publication(self,request,queryset,publish):
        if not permitted(request,'publish_dic_announcements'): raise PermissionDenied
        editions=list(queryset.order_by().values_list('edition_id',flat=True).distinct())
        if len(editions)!=1:
            self.message_user(request,'Select one camp edition.',messages.ERROR); return
        try:
            with transaction.atomic():
                for pk in queryset.order_by('pk').values_list('pk', flat=True):
                    publish_announcement(editions[0], pk, request.user, 'publish' if publish else 'withdraw')
        except ValidationError as error:
            self.message_user(request, ' '.join(error.messages), messages.ERROR)
    @admin.action(description='Publish selected announcements')
    def publish(self,request,queryset): self.publication(request,queryset,True)
    @admin.action(description='Unpublish selected announcements')
    def unpublish(self,request,queryset): self.publication(request,queryset,False)
    @transaction.atomic
    def save_model(self,request,obj,form,change):
        if not self.has_change_permission(request,obj): raise PermissionDenied
        save_announcement_draft(obj, request.user)
