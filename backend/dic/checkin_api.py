from uuid import UUID
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .operations_api import OperationsBaseView, _edition_from_request
from .campsite_api import require_campsite_staff
from .models import CampEdition
from .checkin_services import (require_checkin_staff, require_checkin_storage,
    checkin_directory, check_in_participant, checkin_summary)


class CampCheckInView(OperationsBaseView):
    def get(self, request):
        require_campsite_staff(request.user)
        printing = request.query_params.get('print') == '1'
        if printing and not request.user.has_perm('dic.can_export_dic_reports'):
            raise PermissionDenied('Report export permission is required to print the check-in list.')
        require_checkin_storage()
        edition = _edition_from_request(request)
        search = request.query_params.get('search', '').strip()
        if len(search) > 200:
            raise ValidationError('Search must be 200 characters or fewer.')
        rows, totals = checkin_directory(edition, search) if edition else ([], None)
        if printing:
            html = render_to_string('dic/checkin_list.html', dict(edition=edition,
                rows=rows, totals=totals, search=search, generated_at=timezone.now()))
            response = HttpResponse(html, content_type='text/html; charset=utf-8')
            response['Cache-Control'] = 'private, no-store'
            return response
        try:
            page = int(request.query_params.get('page', '1'))
            if page < 1:
                raise ValueError
        except ValueError as exc:
            raise ValidationError('Choose a valid page.') from exc
        return Response(dict(edition=dict(id=edition.pk, name=edition.name) if edition else None,
            editions=list(CampEdition.objects.order_by('-year', '-pk').values('id', 'name', 'year')),
            totals=totals, count=len(rows), page=page, page_size=25,
            results=rows[(page-1)*25:page*25]))

    def post(self, request):
        require_checkin_staff(request.user)
        require_checkin_storage()
        # Require an explicit edition for writes, rather than a changing default.
        if not request.query_params.get('edition'):
            raise ValidationError('Choose the camp edition before checking in.')
        edition = _edition_from_request(request)
        if not isinstance(request.data, dict):
            raise ValidationError('Send a participant_id in a JSON object.')
        try:
            participant_id = UUID(str(request.data.get('participant_id', '')))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError('Choose a valid participant.') from exc
        row, created = check_in_participant(edition, participant_id, request.user)
        return Response(dict(created=created, check_in=checkin_summary(row)), status=201 if created else 200)
