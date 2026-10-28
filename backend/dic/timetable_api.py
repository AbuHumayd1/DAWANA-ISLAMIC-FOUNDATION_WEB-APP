from datetime import date
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from .participant_api import PortalView
from .feedback_services import portal_item
from .timetable_models import TimetableEntry
from .timetable_services import LAGOS, dates_for, selected_date
from .operations_api import OperationsBaseView, _edition_from_request
from .models import CampEdition
from django.db.models import Count


class ParticipantTimetableView(PortalView):
    def get(self, request):
        try:
            item_id = int(request.query_params.get('item_id', ''))
        except (ValueError, TypeError):
            raise ValidationError('Choose a participant.') from None
        item = portal_item(request, item_id)
        kind = request.query_params.get('type', 'activities')
        if kind not in dict(TimetableEntry.TYPES):
            raise ValidationError('Unknown timetable type.')
        if TimetableEntry._meta.db_table not in connection.introspection.table_names():
            error = APIException('Timetable setup is pending. Please check again later.')
            error.status_code = 503
            raise error
        edition = item.order.edition
        # The edition comes solely from the eligible, session-scoped booking item.
        published = TimetableEntry.objects.filter(edition=edition, timetable_type=kind, status='published')
        published_dates = set(published.values_list('date', flat=True))
        now = timezone.localtime(timezone.now(), LAGOS)
        try:
            raw = request.query_params.get('date')
            day = selected_date(edition, published_dates, date.fromisoformat(raw) if raw else None, now)
        except (ValueError, DjangoValidationError):
            raise ValidationError('Choose a valid date in this camp edition.') from None
        rows = list(published.filter(date=day))
        current = next((r.pk for r in rows if day == now.date() and r.start_time and r.end_time
                        and r.start_time <= now.time() < r.end_time), None)
        upcoming = next((r.pk for r in sorted(rows, key=lambda r: (r.start_time is None, r.start_time))
                         if r.start_time and (day > now.date() or day == now.date() and r.start_time > now.time())), None)
        return Response(dict(edition=edition.pk, edition_name=edition.name, type=kind,
            today=str(now.date()), date=str(day), timezone='Africa/Lagos', current=current, upcoming=upcoming,
            dates=[dict(date=str(d), published=d in published_dates) for d in dates_for(edition)],
            state='published' if rows else 'unpublished',
            entries=[dict(id=r.pk, day_number=r.day_number, time_label=r.time_label,
                start_time=r.start_time.isoformat() if r.start_time else None,
                end_time=r.end_time.isoformat() if r.end_time else None,
                description=r.description, certainty=r.certainty, location=r.location,
                instructions=r.instructions) for r in rows]))


class OperationsTimetableView(OperationsBaseView):
    def get(self, request):
        user = request.user
        if not any(user.has_perm('dic.' + p) for p in ('view_timetableentry', 'manage_dic_timetables', 'publish_dic_timetables')):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Explicit timetable access is required.')
        from django.urls import reverse
        metadata = dict(editions=list(CampEdition.objects.order_by('-year').values('id', 'name')),
            admin_url=reverse('admin:dic_timetableentry_changelist'),
            can_edit=user.has_perm('dic.manage_dic_timetables'), can_publish=user.has_perm('dic.publish_dic_timetables'))
        if not request.query_params.get('edition'):
            return Response(dict(**metadata, days=[], setup_pending=False))
        edition = _edition_from_request(request)
        if TimetableEntry._meta.db_table not in connection.introspection.table_names():
            return Response(dict(**metadata, days=[], setup_pending=True))
        rows = TimetableEntry.objects.filter(edition=edition).values('date', 'timetable_type', 'status').annotate(entries=Count('pk')).order_by('date', 'timetable_type')
        return Response(dict(**metadata, days=list(rows), setup_pending=False))
