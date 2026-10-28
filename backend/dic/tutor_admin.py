"""Explicitly permissioned Admin commands. Invitation tokens appear once only."""
from django import forms
from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.conf import settings
from rest_framework.exceptions import ValidationError
from .recovery import normalize_email
from .models import TutorRegistrationAuthorization
from .tutor_registration import authorize, issue, revoke, require_authorizer, can_authorize_tutors


class TutorAuthorizationForm(forms.ModelForm):
    action_reason = forms.CharField(required=False, widget=forms.Textarea,
        help_text='Required when issuing/reissuing or revoking using the buttons below.')
    invitation_origin = forms.ChoiceField(required=False,
        help_text='Choose the public frontend origin when it differs from the Admin server.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['invitation_origin'].choices = [('', 'Same origin as this Admin server')] + [
            (origin, origin) for origin in settings.CORS_ALLOWED_ORIGINS]

    def clean_email(self):
        return normalize_email(self.cleaned_data['email'])

    def clean(self):
        data = super().clean()
        if ('_issue_tutor' in self.data or '_revoke_tutor' in self.data) and not data.get('action_reason', '').strip():
            raise forms.ValidationError('An action reason is required.')
        return data

    class Meta:
        model = TutorRegistrationAuthorization
        fields = ['edition', 'intended_name', 'email', 'reason']


@admin.register(TutorRegistrationAuthorization)
class TutorAuthorizationAdmin(admin.ModelAdmin):
    form = TutorAuthorizationForm
    list_display = ('intended_name', 'edition', 'email', 'authorized_by', 'expires_at', 'redeemed_at', 'revoked_at')
    change_form_template = 'admin/dic/tutor_authorization.html'
    readonly_fields = ('authorized_by', 'authorized_at', 'issued_at', 'expires_at', 'verified_at', 'redeemed_at', 'enrollment', 'revoked_at', 'revoked_by', 'revocation_reason')

    def has_module_permission(self, request):
        return can_authorize_tutors(request.user)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('edition', 'intended_name', 'email', 'reason') if obj else ())

    def save_model(self, request, obj, form, change):
        require_authorizer(request.user)
        if not change:
            created = authorize(request.user, obj.edition, obj.intended_name, obj.email, obj.reason)
            obj.__dict__.update(created.__dict__)

    def response_change(self, request, obj):
        reason = request.POST.get('action_reason', '').strip()
        if '_issue_tutor' in request.POST:
            try:
                token = issue(request.user, obj.pk, reason)
            except ValidationError:
                return HttpResponse('Invitation could not be issued. Refresh and review authorization status.', status=400)
            origin = request.POST.get('invitation_origin', '')
            if origin not in settings.CORS_ALLOWED_ORIGINS:
                origin = ''
            # Relative fragment prevents server/access logs receiving the credential.
            response = HttpResponse(format_html('<h1>Copy this invitation once</h1><p>Send privately to the authorized tutor. It expires in seven days.</p><a href="{}/dic/register#tutor={}">Tutor registration invitation</a>', origin.rstrip('/'), token))
            response['Cache-Control'] = 'no-store'
            response['Referrer-Policy'] = 'no-referrer'
            return response
        if '_revoke_tutor' in request.POST:
            try:
                revoke(request.user, obj.pk, reason)
            except ValidationError:
                return HttpResponse('Authorization changed. Refresh and retry revocation with a reason.', status=400)
        return super().response_change(request, obj)
