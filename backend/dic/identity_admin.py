from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import CampEnrollment, DigitalIDIssue, GuardianRelationship, DICAdminAuditEvent, HousingJob, HouseAllocation
from .identity_cards import command, require_staff, current_issue, housing
from .identity_views import render_cards
from .participant_services import eligibility, id_summary, record
from .housing_policy import age_band, age_on


class PortraitForm(forms.ModelForm):
    class Meta:
        model = CampEnrollment
        fields = ['portrait']
        widgets = {'portrait': forms.FileInput()}


@admin.register(CampEnrollment)
class ParticipantDirectoryAdmin(admin.ModelAdmin):
    form = PortraitForm
    list_display = ('participant_number', 'participant_name', 'edition', 'age_category', 'registration_state',
                    'verified_payment', 'accommodation', 'allocation_state', 'guardian', 'id_state', 'qr_state', 'card_links')
    list_filter = ('edition', 'source_item__order__status', 'source_item__order__payment_status')
    search_fields = ('participant_number', 'participant__full_name')
    list_per_page = 25
    actions = ('issue_and_print', 'print_selected', 'print_a6_selected', 'print_a6_standard')
    readonly_fields = ('participant_number', 'participant_name', 'edition', 'age_category', 'registration_state',
                       'verified_payment', 'accommodation', 'allocation_state', 'guardian', 'id_state', 'qr_state', 'last_verification',
                       'card_links', 'portrait_state')

    def get_fields(self, request, obj=None):
        return list(self.readonly_fields) + (['portrait'] if self.has_manage_ids_permission(request) else [])

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('participant', 'edition', 'source_item__order')

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff and request.user.has_perm('dic.can_view_dic_ids')

    def has_manage_ids_permission(self, request):
        return self.has_view_permission(request) and request.user.has_perm('dic.can_manage_dic_ids')

    def has_change_permission(self, request, obj=None):
        return self.has_manage_ids_permission(request)

    def has_add_permission(self, request):
        return False  # Reuse ensure_enrollment from actual registration items.

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Full name')
    def participant_name(self, obj):
        return obj.participant.full_name

    @admin.display(description='Age category')
    def age_category(self, obj):
        if obj.source_item.order.registration_basis == 'tutor':
            return 'Adult tutor'
        try:
            return ('0–5', '6–10', '11–13', '14–16', '17+')[age_band(obj.participant, obj.edition)]
        except DjangoValidationError:
            return 'Reference date / birth record needs review'

    @admin.display(description='Registration')
    def registration_state(self, obj):
        return obj.source_item.order.get_status_display()

    @admin.display(description='Verified-payment / eligibility')
    def verified_payment(self, obj):
        result = eligibility(obj)
        return result['code'].replace('_', ' ').title()

    @admin.display(description='Housing allocation')
    def accommodation(self, obj):
        return housing(obj)

    @admin.display(description='Allocation / queue status')
    def allocation_state(self, obj):
        if obj.source_item.order.registration_basis == 'tutor':
            return 'Not applicable (tutor)'
        latest = HouseAllocation.objects.filter(edition=obj.edition, participant=obj.participant).order_by('-allocated_at', '-pk').first()
        job = HousingJob.objects.filter(edition=obj.edition, participant=obj.participant).first()
        state = latest.get_status_display() if latest else 'Not allocated'
        return state + (' · ' + job.get_state_display() if job else '')

    def guardian(self, obj):
        if obj.source_item.order.registration_basis == 'tutor':
            return 'Not applicable (adult tutor)'
        link = GuardianRelationship.objects.filter(edition=obj.edition, child=obj.participant, status='approved').select_related('guardian').first()
        if link:
            return link.guardian.full_name + ' (approved)'
        try:
            return 'Awaiting guardian review' if age_on(obj.participant, obj.edition) <= 5 else 'Not applicable'
        except DjangoValidationError:
            return 'Age policy needs review'

    @admin.display(description='Digital ID')
    def id_state(self, obj):
        summary = id_summary(obj)
        if summary['issue'] and summary['issue']['status'] == 'current' and not summary['eligibility']['eligible']:
            return 'Inactive — eligibility review required'
        return summary['issue']['status'] if summary['issue'] else 'Pending issuance'

    @admin.display(description='QR credential')
    def qr_state(self, obj):
        issue = current_issue(obj)
        if issue and issue.expires_at > timezone.now() and eligibility(obj)['eligible']:
            return 'Active' if issue.verification_digest else 'Legacy ID — activate QR using Issue'
        return 'Unavailable / pending'

    def last_verification(self, obj):
        event = DICAdminAuditEvent.objects.filter(action='participant_qr_verified', target_id=str(obj.pk)).first()
        return event.created_at if event else 'No verification recorded'

    def portrait_state(self, obj):
        return 'Private portrait on file' if obj.portrait else 'No portrait supplied — card remains usable'

    @admin.display(description='Card controls')
    def card_links(self, obj):
        url = reverse('dic:id-card', args=[obj.pk])
        return format_html('<a href="{}">PVC view / print</a> · <a href="{}?format=a6">A6 view / print</a> · <a href="{}?download=1">PVC HTML</a> · <a href="{}?format=a6&amp;download=1">A6 HTML</a> · <a href="{}">Issue / replace / revoke</a>',
            url, url, url, url, reverse('admin:dic_id_manage', args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        require_staff(request.user, manage=True)
        obj.save(update_fields=['portrait'])
        record('participant_portrait_updated', obj, request.user, supplied=bool(obj.portrait))

    def get_urls(self):
        return [path('<uuid:pk>/manage/', self.admin_site.admin_view(self.manage), name='dic_id_manage')] + super().get_urls()

    def manage(self, request, pk):
        require_staff(request.user, manage=True)
        obj = get_object_or_404(CampEnrollment.objects.select_related('participant', 'edition'), pk=pk)
        if request.method == 'POST':
            try:
                command(obj, request.POST.get('operation', ''), request.user, request.POST.get('reason', '').strip())
            except ValidationError:
                self.message_user(request, 'ID operation blocked: verify eligibility, validity dates and a replacement/revocation reason (maximum 240 characters).', messages.ERROR)
            else:
                self.message_user(request, 'ID operation recorded. Existing QR credentials are invalid after revocation/replacement.', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:dic_campenrollment_change', args=[pk]))
        return TemplateResponse(request, 'admin/dic/identity_manage.html', {
            **self.admin_site.each_context(request), 'title': 'Participant ID management', 'object': obj,
            'opts': self.model._meta, 'status': self.id_state(obj), 'eligibility': self.verified_payment(obj),
        })

    @admin.action(description='Issue eligible selected IDs and open print sheet (maximum 25)', permissions=['manage_ids'])
    def issue_and_print(self, request, queryset):
        require_staff(request.user, manage=True)
        if queryset.count() > 25:
            self.message_user(request, 'Select at most 25 participant records.', messages.ERROR)
            return
        for obj in queryset:
            try:
                command(obj, 'issue', request.user, 'Authorized staff batch issuance.')
            except ValidationError:
                self.message_user(request, f'{obj.participant_number}: eligibility or replacement review required.', messages.WARNING)
        return render_cards(request, list(queryset), batch=True)

    @admin.action(description='A4 batch print / download selected active cards (maximum 25)', permissions=['view'])
    def print_selected(self, request, queryset):
        require_staff(request.user)
        if queryset.count() > 25:
            self.message_user(request, 'Select at most 25 participant records.', messages.ERROR)
            return
        return render_cards(request, list(queryset), batch=True)

    @admin.action(description='A6 badges: four-up borderless A4 (existing active IDs only)', permissions=['view'])
    def print_a6_selected(self, request, queryset):
        return self.a6_batch(request, queryset, 'borderless')

    @admin.action(description='A6 badges: two-up landscape A4 for standard printers', permissions=['view'])
    def print_a6_standard(self, request, queryset):
        return self.a6_batch(request, queryset, 'standard')

    def a6_batch(self, request, queryset, printer):
        require_staff(request.user)
        if queryset.count() > 25:
            self.message_user(request, 'Select at most 25 participant records.', messages.ERROR)
            return
        return render_cards(request, list(queryset), batch=True, card_format='a6', printer=printer)


@admin.register(DigitalIDIssue)
class IDHistoryAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'version', 'created_at', 'issued_by', 'expires_at', 'revoked_at', 'revoked_by')
    list_filter = ('enrollment__edition', 'revoked_at')
    search_fields = ('enrollment__participant_number', 'enrollment__participant__full_name')
    readonly_fields = ('id', 'enrollment', 'version', 'created_at', 'expires_at', 'issued_by', 'revoked_at', 'revoked_by', 'reason')
    fields = readonly_fields  # Never display raw/encrypted QR credentials or digests.

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff and request.user.has_perm('dic.can_view_dic_ids')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
