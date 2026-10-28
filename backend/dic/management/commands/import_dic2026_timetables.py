"""Read-only unless a separately approved operator explicitly supplies --apply."""
import hashlib
import json
from datetime import date, time
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from dic.models import CampEdition, DICAdminAuditEvent, TimetableEntry
from dic.timetable_services import require_staff

SOURCE = Path(__file__).resolve().parents[2] / 'data' / 'dic2026_timetables.json'


def source_rows():
    value = json.loads(SOURCE.read_text(encoding='utf-8'))
    for row in value['entries']:
        row['date'] = date.fromisoformat(row['date'])
        for field in ('start_time', 'end_time'):
            row[field] = time.fromisoformat(row[field]) if row[field] else None
    return value


def import_rows(edition, actor, data):
    """Caller holds the edition lock. A durable receipt preserves staff deletions too."""
    receipt = dict(action='timetable_source_imported', target_type='CampEdition', target_id=str(edition.pk))
    if DICAdminAuditEvent.objects.filter(**receipt).exists():
        return 0
    created = 0
    for row in data['entries']:
        if TimetableEntry.objects.filter(edition=edition, source_key=row['source_key']).exists():
            continue
        TimetableEntry.objects.create(edition=edition, modified_by=actor, status='draft', **row)
        created += 1
    DICAdminAuditEvent.objects.create(actor=actor, **receipt, details={
        'sources': data['sources'], 'count': created,
        'seed_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest()})
    return created


class Command(BaseCommand):
    help = 'Preview DIC 2026 source data. Import drafts only after separate approval; never overwrites edits.'

    def add_arguments(self, parser):
        parser.add_argument('--edition', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--database-name')
        parser.add_argument('--approved-by', help='Username of the staff operator with explicit timetable edit permission')
        parser.add_argument('--approved-seed-sha256', help='Reviewed exact seed file SHA-256; required for writes')

    def handle(self, *args, **options):
        data = source_rows()
        if not options['apply']:
            self.stdout.write(f"PREVIEW ONLY: {len(data['entries'])} draft entries, ten dates, two timetables. No database accessed.")
            return
        if not options['approved_by'] or not options['database_name']:
            raise CommandError('Separate approval, named staff operator and exact database name are required.')
        if options.get('approved_seed_sha256') != hashlib.sha256(SOURCE.read_bytes()).hexdigest():
            raise CommandError('Exact reviewed seed SHA-256 is required before any database access.')
        if data.get('review_status') != 'reconciled_operator_2026_10_28':
            raise CommandError('Source reconciliation is not approved.')
        if connection.settings_dict['NAME'] != options['database_name']:
            raise CommandError('Database identity mismatch.')
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                if cursor.fetchone()[0] != options['database_name']:
                    raise CommandError('Connected database identity mismatch.')
        actor = get_user_model().objects.get(username=options['approved_by'])
        require_staff(actor, 'manage_dic_timetables')
        with transaction.atomic():
            edition = CampEdition.objects.select_for_update().get(pk=options['edition'])
            if edition.year != 2026 or (edition.camp_start_date, edition.camp_end_date) != (date(2026, 12, 23), date(2027, 1, 1)):
                raise CommandError('Choose the DIC 2026 edition with the exact approved camp dates.')
            count = import_rows(edition, actor, data)
        self.stdout.write(f'{count} draft entries imported. Existing edits/deletions preserved. Nothing published.')
