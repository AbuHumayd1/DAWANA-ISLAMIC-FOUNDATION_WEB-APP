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
    from .camp_content import overlap
    for index,left in enumerate(bounded):
        for right in bounded[index+1:]:
            if overlap(left,right):
                raise ValidationError('Overlapping timetable entries for the same audience cannot be published.')
    for row in rows:
        row.full_clean()


@transaction.atomic
def publish_days(user, queryset, publish, *, allow_provisional=False):
    require_staff(user, 'publish_dic_timetables')
    scopes = list(queryset.order_by().values_list('edition_id', 'timetable_type').distinct())
    if len(scopes) != 1:
        raise ValidationError('Select exactly one edition and one timetable type per publication action.')
    edition_id, kind = scopes[0]
    CampEdition.objects.select_for_update().get(pk=edition_id)
    days = list(queryset.order_by().values_list('date', flat=True).distinct())
    rows = list(TimetableEntry.objects.select_for_update().filter(edition_id=edition_id,
        timetable_type=kind, date__in=days))
    if publish and allow_provisional:
        # Owner-authorized full DIC 2026 release: retain source certainty labels.
        # This opt-in is unavailable to ordinary publication actions or other editions.
        edition = CampEdition.objects.get(pk=edition_id)
        if not (user.is_superuser and kind == 'activities'
                and edition.year == 2026
                and str(edition.camp_start_date) == '2026-12-23'
                and str(edition.camp_end_date) == '2027-01-01'):
            raise PermissionDenied('Provisional timetable release requires DIC 2026 superuser approval.')
        if (any(r.certainty == 'proposed' for r in rows)
                or any('millionaire' in (r.title + ' ' + r.description).lower() for r in rows)):
            raise ValidationError('Excluded or proposed activities must be resolved before release.')
    if publish and not allow_provisional:
        # A complete-day publication is not an approval of an imported
        # committee-review draft. In particular, DIC 2026 has 144
        # unspecified activities, including two excluded games.
        # Refuse the ENTIRE operation rather than silently publish them or
        # partially publish a day that staff can no longer edit.
        if any(r.certainty != 'confirmed' for r in rows):
            raise ValidationError(
                'Timetable includes unconfirmed entries on the selected days. '
                'Review and confirm or remove every entry in each day before publishing.'
            )
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
        details={'type': kind, 'days': [str(d) for d in days], 'entries': len(rows),
                 'owner_authorized_provisional_release': bool(publish and allow_provisional),
                 'remaining_unspecified': sum(r.certainty == 'unspecified' for r in rows)})
    return len(rows)
