"""Participant-only admin credential handling; staff policy remains Django's."""
from django.contrib.auth.forms import AdminPasswordChangeForm
from rest_framework.exceptions import ValidationError


def participant_identity(user):
    if not user.pk or user.is_staff or user.is_superuser:
        return False
    from dic.models import PortalAccount
    return PortalAccount.objects.filter(user=user).exists()


class ParticipantAwarePasswordChangeForm(AdminPasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        if participant_identity(user):
            for name in ('password1', 'password2'):
                self.fields[name].help_text = 'Any nonempty password, up to 128 characters. A longer memorable password is safer.'
                self.fields[name].widget.attrs['maxlength'] = 128

    def validate_password_for_user(self, user, password_field_name='password2'):
        if not participant_identity(user):
            return super().validate_password_for_user(user, password_field_name=password_field_name)
        if self.cleaned_data.get('set_usable_password', True):
            from dic.portal_accounts import password_policy
            try:
                password_policy(self.cleaned_data.get(password_field_name), user)
            except ValidationError:
                self.add_error(password_field_name, 'Enter a nonempty password of at most 128 characters.')
