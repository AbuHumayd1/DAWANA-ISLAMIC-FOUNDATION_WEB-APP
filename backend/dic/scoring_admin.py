"""Django Admin access to the existing append-only scoring services."""
import uuid
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException
from .models import CampEdition, House, HouseScoreTransaction
from .scoring_services import require_scoring_staff, record_score, reverse_score, scoring_houses, combined_leaderboard


class ScoreForm(forms.Form):
    edition = forms.ModelChoiceField(CampEdition.objects.all())
    house = forms.ModelChoiceField(House.objects.filter(purpose='participants'))
    entry_type = forms.ChoiceField(choices=[('award', 'Award'), ('deduction', 'Deduction')])
    points = forms.IntegerField(min_value=1, max_value=2147483647)
    activity = forms.CharField(max_length=200, label='Activity or reason')
    note = forms.CharField(max_length=1000, required=False, widget=forms.Textarea)
    request_id = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)


class ReversalForm(forms.Form):
    reason = forms.CharField(max_length=1000, widget=forms.Textarea)
    request_id = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)


@admin.register(HouseScoreTransaction)
class HouseScoreAdmin(admin.ModelAdmin):
    change_list_template = 'admin/dic/score_list.html'
    list_display = ('house', 'edition', 'activity', 'entry_type', 'points', 'created_by', 'created_at', 'correction')
    list_filter = ('edition', 'house', 'entry_type')
    search_fields = ('house__name', 'activity', 'note')
    list_select_related = ('house', 'edition', 'created_by')
    readonly_fields = tuple(field.name for field in HouseScoreTransaction._meta.fields)
    actions = None

    def permitted(self, request, permission='can_view_dic_scores'):
        try:
            require_scoring_staff(request.user, permission)
            return True
        except APIException:
            return False

    def has_view_permission(self, request, obj=None):
        return self.permitted(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Correction')
    def correction(self, obj):
        if obj.reverses_id:
            return 'Reversal'
        return format_html('<a href="{}">Review correction</a>', reverse('admin:dic_score_reverse', args=[obj.pk]))

    def get_urls(self):
        return [
            path('record/', self.admin_site.admin_view(self.record), name='dic_score_record'),
            path('standings/', self.admin_site.admin_view(self.standings), name='dic_score_standings'),
            path('<int:pk>/reverse/', self.admin_site.admin_view(self.correct), name='dic_score_reverse'),
        ] + super().get_urls()

    def form_view(self, request, title, form, submit):
        if request.method == 'POST' and form.is_valid():
            try:
                submit(form.cleaned_data)
            except APIException as exc:
                form.add_error(None, str(exc.detail))
            else:
                self.message_user(request, 'House points recorded.', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:dic_housescoretransaction_changelist'))
        return TemplateResponse(request, 'admin/dic/score_form.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': title, 'form': form,
        })

    def record(self, request):
        if not self.permitted(request, 'can_record_dic_scores'):
            raise PermissionDenied
        def submit(data):
            record_score(data['edition'], request.user, {**data, 'house': data['house'].pk})
        return self.form_view(request, 'Award or deduct house points', ScoreForm(request.POST or None), submit)

    def correct(self, request, pk):
        if not self.permitted(request, 'can_correct_dic_scores'):
            raise PermissionDenied
        from django.shortcuts import get_object_or_404
        entry = get_object_or_404(HouseScoreTransaction, pk=pk)
        return self.form_view(request, 'Reverse house points: ' + entry.activity,
            ReversalForm(request.POST or None), lambda data: reverse_score(entry.edition, request.user, pk, data))

    def standings(self, request):
        if not self.permitted(request):
            raise PermissionDenied
        edition = CampEdition.objects.filter(pk=request.GET.get('edition')).first() if request.GET.get('edition', '').isdigit() else CampEdition.objects.filter(is_active=True).first()
        rows = combined_leaderboard(scoring_houses(edition), HouseScoreTransaction.objects.filter(edition=edition)) if edition else []
        return TemplateResponse(request, 'admin/dic/score_standings.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'House rankings', 'editions': CampEdition.objects.order_by('-year'), 'edition': edition, 'rows': rows,
        })
