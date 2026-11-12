from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User
from .participant_admin import ParticipantAwarePasswordChangeForm, participant_identity


class ParticipantAwareUserAdmin(UserAdmin):
    change_password_form = ParticipantAwarePasswordChangeForm

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        # Portal identifiers must change together with their canonical key via
        # the existing staff-reviewed credential transition, never one side only.
        return (*fields, 'username') if obj and participant_identity(obj) else fields


admin.site.register(User, ParticipantAwareUserAdmin)
