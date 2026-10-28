from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from .models import CampEdition, DICAdminAuditEvent
from .timetable_models import TimetableEntry
from .timetable_services import publish_days


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ('edition', 'timetable_type', 'date', 'day_number', 'time_label', 'description', 'display_order', 'status', 'modified_by', 'preview')
    list_filter = ('edition', 'timetable_type', 'date', 'status')
    search_fields = ('description', 'time_label')
    ordering = ('edition', 'timetable_type', 'date', 'display_order')
    readonly_fields = ('status', 'source_key', 'modified_by', 'published_by', 'published_at', 'created_at', 'updated_at')
    actions = ('publish_selected_days', 'unpublish_selected_days')

    def permitted(self, request, permission):
        return request.user.is_active and request.user.is_staff and request.user.has_perm('dic.' + permission)

    def has_module_permission(self, request): return self.has_view_permission(request)
    def has_view_permission(self, request, obj=None):
        return self.permitted(request, 'view_timetableentry') or self.permitted(request, 'manage_dic_timetables') or self.permitted(request, 'publish_dic_timetables')
    def has_add_permission(self, request): return self.permitted(request, 'manage_dic_timetables')
    def has_change_permission(self, request, obj=None):
        return self.permitted(request, 'manage_dic_timetables') and (obj is None or obj.status == 'draft')
    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('edition', 'date', 'timetable_type', 'day_number') if obj else ())

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.permitted(request, 'publish_dic_timetables'):
            actions.pop('publish_selected_days', None)
            actions.pop('unpublish_selected_days', None)
        return actions

    def publication(self, request, queryset, publish):
        try:
            count = publish_days(request.user, queryset, publish)
        except ValidationError as error:
            self.message_user(request, '; '.join(error.messages), messages.ERROR)
        else:
            self.message_user(request, f'{count} entries updated. All entries on the selected days were included.')

    @admin.action(description='Publish complete selected days (one edition and type)')
    def publish_selected_days(self, request, queryset): self.publication(request, queryset, True)
    @admin.action(description='Unpublish complete selected days (one edition and type)')
    def unpublish_selected_days(self, request, queryset): self.publication(request, queryset, False)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not self.has_change_permission(request, obj) or not self.permitted(request, 'manage_dic_timetables'):
            raise PermissionDenied
        CampEdition.objects.select_for_update().get(pk=obj.edition_id)
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
        self.audit(request, obj, 'timetable_draft_saved')

    def audit(self, request, obj, action):
        DICAdminAuditEvent.objects.create(actor=request.user, action=action, target_type='TimetableEntry',
            target_id=str(obj.pk), details={'edition': obj.edition_id, 'type': obj.timetable_type, 'date': str(obj.date)})

    @transaction.atomic
    def delete_model(self, request, obj):
        CampEdition.objects.select_for_update().get(pk=obj.edition_id)
        obj.refresh_from_db()
        if not self.has_delete_permission(request, obj): raise PermissionDenied
        self.audit(request, obj, 'timetable_draft_deleted')
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset: self.delete_model(request, obj)

    @admin.display(description='Full day')
    def preview(self, obj):
        return format_html('<a href="{}">Preview day</a>', reverse('admin:dic_timetable_day', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:pk>/day/', self.admin_site.admin_view(self.day_preview), name='dic_timetable_day')] + super().get_urls()

    def day_preview(self, request, pk):
        if not self.has_view_permission(request): raise PermissionDenied
        obj = self.get_object(request, pk)
        if obj is None:
            from django.http import Http404
            raise Http404
        rows = TimetableEntry.objects.filter(edition=obj.edition, timetable_type=obj.timetable_type, date=obj.date)
        body = format_html_join('', '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>',
            ((r.time_label, r.description or '(Source description unspecified)', r.certainty, r.status) for r in rows))
        return HttpResponse(format_html('<!doctype html><html><meta name="viewport" content="width=device-width"><title>Day preview</title><body><h1>{} — {} — {}</h1><p>Staff preview includes drafts. Africa/Lagos.</p><table><tr><th>Period</th><th>Description</th><th>Source certainty</th><th>Publication</th></tr>{}</table></body></html>', obj.edition, obj.get_timetable_type_display(), obj.date, body))
