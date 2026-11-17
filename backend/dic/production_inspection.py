"""Read-only DIC 2026 production inventory for authenticated Django superusers.

This diagnostic is deliberately separate from the population command.
Never mutate records, approve housing, or disclose secrets or participants.
"""
import hashlib
import json
from collections import Counter
from datetime import date

from django.db import connection
from django.db.models import Count
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.utils.cache import patch_cache_control

from .management.commands.initialize_dic2026_release import (
    HOUSING_REFERENCE_DATE, LEGACY_KEYS, SOURCE, canonical,
)
from .house_configuration import approved_2026_houses
from .models import (
    AcademicClass, CampEdition, CertificateRelease, DICAdminAuditEvent,
    GuardianRelationship, House, HouseAllocation, HousingJob, RegistrationOrder,
    TimetableEntry,
)

EXPECTED_START = date(2026, 12, 23)
EXPECTED_END = date(2027, 1, 1)



def housing_activation_preflight(edition):
    """Read-only gate matching the actual workerless housing entry point.

    Report only booleans and safe operator-facing reasons; never expose actor
    identifiers, secrets, individual campers, payment references or fingerprints.
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied, ValidationError
    from .allocation import AllocationError, allocation_configuration_fingerprint
    from .housing_service import permitted, validate_inventory

    blockers = []
    if getattr(settings, 'DAWANA_WEBSITE_ONLY', False):
        blockers.append('Full application mode is not enabled.')
    actor_id = getattr(settings, 'DIC_AUTOMATION_ACTOR_ID', 0)
    if type(actor_id) is not int or actor_id <= 0:
        blockers.append('Housing automation actor is not configured.')
    else:
        actor = get_user_model().objects.filter(
            pk=actor_id, is_active=True, is_staff=True
        ).first()
        if actor is None:
            blockers.append('Housing automation actor is not active staff.')
        else:
            for permission in ('can_process_housing_queue', 'can_allocate_participants'):
                try:
                    permitted(actor, permission)
                except PermissionDenied:
                    blockers.append('Housing automation actor lacks ' + permission + '.')
    if edition.allocation_strategy != 'balanced':
        blockers.append('Select the balanced housing strategy.')
    if not (edition.allocation_strategy_approved_at
            and edition.allocation_strategy_approved_by_id
            and edition.allocation_strategy_approval_note.strip()):
        blockers.append('Committee housing approval has not been recorded.')
    if not edition.allocation_approved_configuration or (
        edition.allocation_approved_configuration != allocation_configuration_fingerprint(edition)
    ):
        blockers.append('Current housing configuration fingerprint is not approved.')
    try:
        validate_inventory(edition)
    except (ValidationError, AllocationError):
        blockers.append('Housing inventory or existing allocations require supervisor review.')
    return {'ready': not blockers, 'blockers': blockers, 'mode': 'read_only'}

def production_inspection(request):
    """Superuser-only GET. Runs SELECTs only; never attempts an initialization."""
    if request.method != 'GET':
        response = HttpResponseNotAllowed(['GET'])
    elif not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff or not request.user.is_superuser:
        response = HttpResponseForbidden('A signed-in Django superuser is required.')
    else:
        edition = CampEdition.objects.filter(year=2026).first()
        source = json.loads(SOURCE.read_text(encoding='utf-8'))
        expected = approved_2026_houses()
        result = {
            'mode': 'read_only_no_database_changes',
            'database': {'name': str(connection.settings_dict['NAME']), 'engine': connection.vendor},
            'source': {
                'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'expected_houses': len(expected),
                'expected_timetable_total': len(source['entries']),
                'expected_activities': sum(x['timetable_type'] == 'activities' for x in source['entries']),
                'expected_food': sum(x['timetable_type'] == 'food' for x in source['entries']),
            },
            'edition': None,
            'houses': [],
            'timetables': None,
            'academic_classes': [],
            'housing_jobs': {},
            'guardian_relationships': {},
            'allocations': {'allocated': 0, 'history': 0},
            'registration_orders': {},
            'population_receipt': False,
            'issues': [],
            'ready_for_population_review': False,
            'housing_activation': None,
        }
        issues = result['issues']
        if edition is None:
            issues.append('DIC 2026 edition is missing; do not run population.')
        else:
            result['edition'] = {
                'id': edition.pk, 'name': edition.name, 'year': edition.year,
                'camp_start': edition.camp_start_date.isoformat(),
                'camp_end': edition.camp_end_date.isoformat(),
                'is_active': edition.is_active,
                'housing_age_reference_date': (
                    edition.housing_age_reference_date.isoformat()
                    if edition.housing_age_reference_date else None
                ),
                'allocation_strategy': edition.allocation_strategy,
                'strategy_approved': bool(edition.allocation_strategy_approved_at),
                'configuration_fingerprint_approved': bool(edition.allocation_approved_configuration),
            }
            if edition.camp_start_date != EXPECTED_START or edition.camp_end_date != EXPECTED_END:
                issues.append('Edition dates differ from the approved 23 Dec 2026–1 Jan 2027 period.')
            if edition.housing_age_reference_date not in (None, HOUSING_REFERENCE_DATE):
                issues.append('Housing age reference date conflicts with the approved date.')
            houses = list(House.objects.filter(edition=edition).order_by('pk').values(
                'id', 'name', 'canonical_key', 'gender', 'purpose', 'status',
                'capacity', 'badge_colour', 'reserve_designation', 'eligibility_rules',
            ))
            result['houses'] = houses
            keys = Counter(canonical(house['name']) for house in houses if house['purpose'] == 'participants')
            expected_keys = {canonical(row['name']) for row in expected}
            if any(k not in expected_keys or n != 1 for k, n in keys.items()):
                issues.append('Existing participant house identities conflict with the approved list.')
            for house in houses:
                if house['purpose'] != 'participants':
                    continue
                matching = next((h for h in expected if canonical(h['name']) == canonical(house['name'])), None)
                if matching and (
                    house['gender'] != matching['gender']
                    or house['status'] != 'active'
                    or house['capacity'] not in (None, 30)
                    or house['badge_colour'] not in ('', matching['badge_colour'])
                    or house['reserve_designation']
                    or bool(house['eligibility_rules'])
                    or house['canonical_key'] not in ('', LEGACY_KEYS[canonical(house['name'])])
                ):
                    issues.append('House configuration conflicts with approved inventory; review in Admin.')
                    break
                if matching and (house['capacity'] is None or not house['badge_colour']) and HouseAllocation.objects.filter(
                    house_id=house['id'], status='allocated'
                ).exists():
                    issues.append('An occupied house has incomplete capacity or badge colour.')
                    break
            timetable = TimetableEntry.objects.filter(edition=edition)
            result['timetables'] = {
                'total': timetable.count(),
                'activities': timetable.filter(timetable_type='activities').count(),
                'food': timetable.filter(timetable_type='food').count(),
                'draft': timetable.filter(status='draft').count(),
                'published': timetable.filter(status='published').count(),
                'approved_source_keys': timetable.filter(source_key__startswith='dic2026:').count(),
            }
            result['academic_classes'] = list(AcademicClass.objects.filter(
                edition=edition).order_by('name').values_list('name', flat=True))
            jobs = HousingJob.objects.filter(edition=edition)
            result['housing_jobs'] = dict(jobs.values_list('state').annotate(n=Count('pk')))
            relations = GuardianRelationship.objects.filter(edition=edition)
            result['guardian_relationships'] = dict(relations.values_list('status').annotate(n=Count('pk')))
            allocations = HouseAllocation.objects.filter(edition=edition)
            result['allocations'] = {
                'allocated': allocations.filter(status='allocated').count(),
                'history': allocations.count(),
            }
            result['registration_orders'] = dict(
                RegistrationOrder.objects.filter(edition=edition)
                .values_list('payment_status').annotate(n=Count('pk'))
            )
            result['population_receipt'] = DICAdminAuditEvent.objects.filter(
                action='dic2026_integrated_reference_initialized',
                target_type='CampEdition', target_id=str(edition.pk),
            ).exists()
            result['certificate_configuration_exists'] = CertificateRelease.objects.filter(edition=edition).exists()
            result['ready_for_population_review'] = not issues
            result['housing_activation'] = housing_activation_preflight(edition)
        response = JsonResponse(result, json_dumps_params={'indent': 2, 'ensure_ascii': False})
    patch_cache_control(response, no_store=True)
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
