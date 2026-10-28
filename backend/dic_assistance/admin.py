from django.contrib import admin
from .models import RegistrationAssistance


@admin.register(RegistrationAssistance)
class AssistanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'edition', 'created_at')
    readonly_fields = ('id', 'actor', 'order', 'edition', 'created_at', 'request_id', 'fingerprint')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser
