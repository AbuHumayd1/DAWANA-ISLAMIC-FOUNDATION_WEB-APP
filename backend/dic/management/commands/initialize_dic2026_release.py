"""Explicit, additive DIC 2026 reference initialization; never runs at startup."""
import hashlib
import json
import re
import unicodedata
from datetime import date, time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from dic.models import (
    AcademicClass, CampEdition, CertificateRelease, DICAdminAuditEvent,
    House, HouseAllocation, TimetableEntry,
)
from dic.house_configuration import approved_2026_houses, house_capacity_limit

SOURCE = Path(__file__).resolve().parents[2] / 'data/dic2026_approved_release.json'
HOUSING_REFERENCE_DATE = date(2026, 12, 23)


def canonical(value):
    return re.sub('[^a-z]', '', unicodedata.normalize('NFKD', value)
                  .encode('ascii', 'ignore').decode().lower())


def approved_houses():
    """One authoritative identity, badge and capacity source for the edition."""
    rows = approved_2026_houses()
    keys = [canonical(row['name']) for row in rows]
    if (len(rows) != 8 or len(set(keys)) != 8
            or sum(row['gender'] == 'male' for row in rows) != 4
            or sum(row['gender'] == 'female' for row in rows) != 4):
        raise CommandError('The approved house inventory must contain four unique houses per sex.')
    limit = house_capacity_limit(type('EditionYear', (), {'year': 2026})())
    for row in rows:
        if (row['capacity'] != limit or row['purpose'] != 'participants'
                or row['status'] != 'active'
                or not re.fullmatch(r'#[0-9a-fA-F]{6}', row['badge_colour'])
                or not row['arabic_name'] or not row['motto']):
            raise CommandError('House configuration must match the approved capacity and identity rules.')
    return rows


def _populate_houses(edition, actor):
    """Reconcile only provably matching identities; never overwrite staff edits."""
    rows = approved_houses()
    existing = list(House.objects.select_for_update().filter(
        edition=edition, purpose='participants'))
    wanted = {canonical(row['name']): row for row in rows}
    mapped = {}
    for house in existing:
        key = canonical(house.name)
        if key not in wanted:
            raise CommandError('Unmatched existing participant house: reconcile in Admin before population.')
        if key in mapped:
            raise CommandError('Duplicate house identity: reconcile in Admin before population.')
        mapped[key] = house
    if edition.housing_age_reference_date not in (None, HOUSING_REFERENCE_DATE):
        raise CommandError('Conflicting housing age reference date; no data changed.')
    # Check every existing house before writing any changes, so conflicts never
    # partially populate an edition or override an administrator's decisions.
    for key, house in mapped.items():
        row = wanted[key]
        if (house.gender != row['gender'] or house.purpose != 'participants'
                or house.status != 'active' or house.reserve_designation
                or house.eligibility_rules
                or house.capacity not in (None, row['capacity'])
                or house.badge_colour not in ('', row['badge_colour'])
                or (house.canonical_key and house.canonical_key != key)):
            raise CommandError('Existing house configuration differs from the approved inventory; review in Admin.')
        if ((house.capacity is None or not house.badge_colour)
                and HouseAllocation.objects.filter(house=house, status='allocated').exists()):
            raise CommandError('An occupied house is not fully configured; supervisor reconciliation required.')
    if edition.housing_age_reference_date is None:
        edition.housing_age_reference_date = HOUSING_REFERENCE_DATE
        edition.save(update_fields=['housing_age_reference_date', 'updated_at'])
    count = 0
    for key, row in wanted.items():
        house = mapped.get(key)
        if house is None:
            House.objects.create(
                edition=edition, canonical_key=key, name=row['name'],
                gender=row['gender'], purpose='participants', status='active',
                capacity=row['capacity'], badge_colour=row['badge_colour'],
                eligibility_notes=('Arabic: ' + row['arabic_name'] +
                                   '\\nColour: ' + row['colour_name'] +
                                   '\\nMotto: ' + row['motto']),
            )
            count += 1
        else:
            updates = {}
            if not house.canonical_key:
                updates['canonical_key'] = key
            if house.capacity is None:
                updates['capacity'] = row['capacity']
            if not house.badge_colour:
                updates['badge_colour'] = row['badge_colour']
            if updates:
                for field, value in updates.items():
                    setattr(house, field, value)
                house.save(update_fields=list(updates))
                count += 1
    if (House.objects.filter(edition=edition, purpose='participants').count() != 8
            or House.objects.filter(edition=edition, purpose='participants',
                                    capacity=30, status='active').count() != 8):
        raise CommandError('Final eight-house inventory validation failed.')
    if count:
        DICAdminAuditEvent.objects.create(
            actor=actor, action='dic2026_houses_populated',
            target_type='CampEdition', target_id=str(edition.pk),
            details={'houses_created_or_completed': count, 'capacity_each': 30,
                     'configuration': 'dic_2026_houses.json'},
        )
    return count


@transaction.atomic
def initialize(edition, actor):
    edition = CampEdition.objects.select_for_update().get(pk=edition.pk)
    if (edition.year != 2026 or edition.camp_start_date != date(2026, 12, 23)
            or edition.camp_end_date != date(2027, 1, 1)):
        raise CommandError('Exact approved DIC 2026 camp dates are required.')
    housing_count = _populate_houses(edition, actor)
    receipt = dict(action='dic2026_integrated_reference_initialized',
                   target_type='CampEdition', target_id=str(edition.pk))
    if DICAdminAuditEvent.objects.filter(**receipt).exists():
        return 0
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    count = 0
    for value in source['entries']:
        row = dict(value)
        row['date'] = date.fromisoformat(row['date'])
        for field in ('start_time', 'end_time'):
            row[field] = time.fromisoformat(row[field]) if row[field] else None
        if TimetableEntry.objects.filter(edition=edition, source_key=row['source_key']).exists():
            continue
        # Preserve manually entered days; never replace staff edits or deletions.
        if TimetableEntry.objects.filter(
            edition=edition, date=row['date'], timetable_type=row['timetable_type']
        ).exclude(source_key__startswith='dic2026:').exists():
            continue
        TimetableEntry.objects.create(edition=edition, modified_by=actor, **row)
        count += 1
    for name in ("Ta'lim", 'Tahdheeb', "Da'wah"):
        AcademicClass.objects.get_or_create(
            edition=edition, name=name, defaults={'modified_by': actor})
    CertificateRelease.objects.get_or_create(edition=edition)
    DICAdminAuditEvent.objects.create(
        actor=actor, **receipt,
        details={'entries': count, 'housing_created_or_completed': housing_count,
                 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
    )
    return count


class Command(BaseCommand):
    help = ('Preview approved reference data; --apply requires exact database, '
            'source checksum and named authorized actor. Timetables remain drafts.')

    def add_arguments(self, parser):
        parser.add_argument('--edition', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--database-name')
        parser.add_argument('--approved-by')
        parser.add_argument('--source-sha256')

    def handle(self, *args, **options):
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        if not options['apply']:
            self.stdout.write(
                'PREVIEW ONLY: approved programme, 27 specified meals, '
                'eight 30-place houses (240 total), and housing reference date '
                '23 Dec 2026. Timetables remain drafts. SHA256 ' + digest)
            return
        if (str(options['database_name']) != str(connection.settings_dict['NAME'])
                or options['source_sha256'] != digest or not options['approved_by']):
            raise CommandError('Exact database, reviewed source hash and authorized actor required.')
        actor = get_user_model().objects.get(
            username=options['approved_by'], is_active=True, is_staff=True)
        if (not actor.has_perm('dic.manage_dic_timetables')
                or not actor.has_perm('dic.add_house')
                or not actor.has_perm('dic.can_approve_allocation_strategy')):
            raise CommandError('Timetable, house and housing configuration permissions required.')
        count = initialize(CampEdition.objects.get(pk=options['edition']), actor)
        self.stdout.write(
            str(count) + ' timetable drafts added; approved houses configured where '
            'safe. Nothing published; allocation approval and worker activation are separate.')
