from datetime import timedelta
from zoneinfo import ZoneInfo
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import CampEdition, DICAdminAuditEvent
from .timetable_models import TimetableEntry

LAGOS = ZoneInfo('Africa/Lagos')


def require_staff(user, permission):
    if not (user.is_active and user.is_staff and user.has_perm('dic.' + permission)):
        raise PermissionDenied('Explicit timetable permission is required.')


def dates_for(edition):
    return [edition.camp_start_date + timedelta(days=i)
            for i in range((edition.camp_end_date - edition.camp_start_date).days + 1)]


def selected_date(edition, published_dates, requested=None, now=None):
    today = timezone.localdate(now, timezone=LAGOS)
    if requested is not None:
        if requested not in dates_for(edition):
            raise ValidationError('Choose a date in this camp edition.')
        return requested
    if edition.camp_start_date <= today <= edition.camp_end_date:
        return today
    future = sorted(day for day in published_dates if day >= today)
    return future[0] if future else max(published_dates, default=edition.camp_start_date)


def validate_day(rows):
    bounded = sorted((r for r in rows if r.start_time and r.end_time), key=lambda r: r.start_time)
    for left, right in zip(bounded, bounded[1:]):
        if left.end_time > right.start_time:
            raise ValidationError('Overlapping timetable entries cannot be published.')
    for row in rows:
        row.full_clean()


@transaction.atomic
def publish_days(user, queryset, publish):
    require_staff(user, 'publish_dic_timetables')
    scopes = list(queryset.order_by().values_list('edition_id', 'timetable_type').distinct())
    if len(scopes) != 1:
        raise ValidationError('Select exactly one edition and one timetable type per publication action.')
    edition_id, kind = scopes[0]
    CampEdition.objects.select_for_update().get(pk=edition_id)
    days = list(queryset.order_by().values_list('date', flat=True).distinct())
    rows = list(TimetableEntry.objects.select_for_update().filter(edition_id=edition_id,
        timetable_type=kind, date__in=days))
    for day in days:
        validate_day([r for r in rows if r.date == day])
    now = timezone.now()
    for row in rows:
        row.status = 'published' if publish else 'draft'
        row.published_by = user if publish else None
        row.published_at = now if publish else None
        row.modified_by = user
        row._publication_action = True
        row.save()
    DICAdminAuditEvent.objects.create(actor=user, action='timetable_published' if publish else 'timetable_unpublished',
        target_type='CampEdition', target_id=str(edition_id),
        details={'type': kind, 'days': [str(d) for d in days], 'entries': len(rows)})
    return len(rows)
