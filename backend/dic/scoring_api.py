from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .operations_api import OperationsBaseView, _edition_from_request
from .models import CampEdition, HouseScoreTransaction
from .scoring_services import (require_scoring_staff, require_scoring_storage, scoring_houses,
    combined_leaderboard, scoring_history_row, record_score, reverse_score)


class ScoreEntryInput(serializers.Serializer):
    house = serializers.IntegerField(min_value=1)
    entry_type = serializers.ChoiceField(choices=('award', 'deduction'))
    points = serializers.IntegerField(min_value=1, max_value=2147483647)
    activity = serializers.CharField(max_length=200)
    note = serializers.CharField(max_length=1000, allow_blank=True, default='')
    request_id = serializers.UUIDField()


class ScoreReversalInput(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
    request_id = serializers.UUIDField()


def write_edition(request):
    if not request.query_params.get('edition'):
        raise ValidationError('Choose the camp edition before recording points.')
    return _edition_from_request(request)


class HouseScoringView(OperationsBaseView):
    def get(self, request):
        require_scoring_staff(request.user)
        printing = request.query_params.get('print')
        if printing and printing not in ('leaderboard', 'history'):
            raise ValidationError('Choose leaderboard or history to print.')
        if printing and not request.user.has_perm('dic.can_export_dic_reports'):
            raise PermissionDenied('Report export permission is required to print scores.')
        require_scoring_storage()
        edition = _edition_from_request(request)
        houses = list(scoring_houses(edition)) if edition else []
        entries = HouseScoreTransaction.objects.filter(edition=edition) if edition else HouseScoreTransaction.objects.none()
        leaderboard = combined_leaderboard(houses, entries)
        history = entries.select_related('house', 'created_by', 'reversal').order_by('-created_at', '-pk')
        if printing:
            response = HttpResponse(render_to_string('dic/scoring_list.html', dict(
                edition=edition, leaderboard=leaderboard, history=[scoring_history_row(row) for row in history] if printing == 'history' else [],
                report=printing, generated_at=timezone.now())), content_type='text/html; charset=utf-8')
            response['Cache-Control'] = 'private, no-store'
            return response
        try:
            page = int(request.query_params.get('page', '1'))
            if page < 1:
                raise ValueError
        except ValueError as exc:
            raise ValidationError('Choose a valid history page.') from exc
        return Response(dict(edition=dict(id=edition.pk, name=edition.name) if edition else None,
            editions=list(CampEdition.objects.order_by('-year', '-pk').values('id', 'name', 'year')),
            leaderboard=leaderboard, count=entries.count(), page=page, page_size=25,
            history=[scoring_history_row(row) for row in history[(page-1)*25:page*25]]))

    def post(self, request):
        require_scoring_staff(request.user, 'can_record_dic_scores')
        require_scoring_storage()
        edition = write_edition(request)
        data = ScoreEntryInput(data=request.data)
        data.is_valid(raise_exception=True)
        row, created = record_score(edition, request.user, data.validated_data)
        return Response(dict(id=row.pk, created=created), status=201 if created else 200)


class HouseScoreReversalView(OperationsBaseView):
    def post(self, request, entry_id):
        require_scoring_staff(request.user, 'can_correct_dic_scores')
        require_scoring_storage()
        edition = write_edition(request)
        data = ScoreReversalInput(data=request.data)
        data.is_valid(raise_exception=True)
        row, created = reverse_score(edition, request.user, entry_id, data.validated_data)
        return Response(dict(id=row.pk, created=created), status=201 if created else 200)
