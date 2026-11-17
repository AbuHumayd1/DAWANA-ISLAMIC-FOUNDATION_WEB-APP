"""Superuser-controlled, one-screen DIC 2026 reference population.

GET previews the exact target and immutable release source. POST requires CSRF,
the reviewed database/edition/checksum and explicit human confirmation.
Never runs on deploy or via GET. Payment and existing participant data untouched.
"""
import hashlib
from datetime import date

from django.core.management.base import CommandError
from django.db import connection
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_http_methods

from .management.commands.initialize_dic2026_release import SOURCE, initialize
from .models import CampEdition, House, TimetableEntry

CONFIRMATION = 'POPULATE DIC 2026'


@require_http_methods(['GET', 'POST'])
def production_population(request):
    if not (request.user.is_authenticated and request.user.is_active
            and request.user.is_staff and request.user.is_superuser):
        return HttpResponseForbidden('Django superuser permission required.')

    edition = CampEdition.objects.filter(year=2026).first()
    name = str(connection.settings_dict['NAME'])
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    state = {
        'title': 'DIC 2026 production population',
        'edition': edition,
        'database_name': name,
        'source_sha256': digest,
        'house_count': House.objects.filter(edition=edition).count() if edition else None,
        'timetable_count': TimetableEntry.objects.filter(edition=edition).count() if edition else None,
        'expected_houses': 8,
        'expected_entries': 182,
        'confirmation': CONFIRMATION,
        'result': None,
        'error': None,
    }

    eligible = (edition is not None and edition.camp_start_date == date(2026, 12, 23)
                and edition.camp_end_date == date(2027, 1, 1))
    if not eligible:
        state['error'] = 'DIC 2026 edition or camp dates do not match the approved release. No data will be changed.'

    if request.method == 'POST':
        if (not eligible
                or request.POST.get('edition_id') != str(edition.pk)
                or request.POST.get('database_name') != name
                or request.POST.get('source_sha256') != digest
                or request.POST.get('confirmation') != CONFIRMATION):
            state['error'] = 'Confirmation, edition, database or source checksum did not match. No data changed.'
        elif not (request.user.has_perm('dic.manage_dic_timetables')
                  and request.user.has_perm('dic.add_house')
                  and request.user.has_perm('dic.can_approve_allocation_strategy')):
            state['error'] = 'Required timetable, housing and allocation approval permissions are missing.'
        else:
            try:
                count = initialize(edition, request.user)
            except CommandError as exc:
                state['error'] = str(exc)
            else:
                state['result'] = ('Reference population finished: %s new timetable entries. '
                                   'House configuration safely reconciled. Verify the numbers below.' % count)
                state['house_count'] = House.objects.filter(edition=edition).count()
                state['timetable_count'] = TimetableEntry.objects.filter(edition=edition).count()

    response = render(request, 'admin/dic/production_population.html', state)
    patch_cache_control(response, no_store=True)
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
