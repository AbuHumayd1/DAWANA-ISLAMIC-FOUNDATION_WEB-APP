"""Publication is a separate approved operation, never part of source import."""
import hashlib
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from dic.models import CampEdition, TimetableEntry, DICAdminAuditEvent
from dic.timetable_services import require_staff, publish_days
from .import_dic2026_timetables import SOURCE, source_rows


class Command(BaseCommand):
    help='Preview source publication requirements; --apply requires exact target, seed approval and publisher.'
    def add_arguments(self,parser):
        parser.add_argument('--edition',type=int,required=True)
        parser.add_argument('--database-name')
        parser.add_argument('--approved-by')
        parser.add_argument('--approved-seed-sha256')
        parser.add_argument('--apply',action='store_true')

    def handle(self,*args,**options):
        data=source_rows(); checksum=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        if not options['apply']:
            self.stdout.write(f'PREVIEW ONLY: {len(data["entries"])} reconciled entries. Seed SHA-256: {checksum}. No database accessed. Publication needs its own approval.')
            return
        if not options.get('database_name') or not options.get('approved_by') or options.get('approved_seed_sha256')!=checksum:
            raise CommandError('Exact target, publisher and reviewed seed SHA-256 are required.')
        if data.get('review_status')!='reconciled_operator_2026_10_28': raise CommandError('Source review is incomplete.')
        if str(connection.settings_dict['NAME'])!=options['database_name']: raise CommandError('Configured database identity mismatch.')
        if connection.vendor!='postgresql': raise CommandError('Publication requires the approved PostgreSQL target.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            if cursor.fetchone()[0]!=options['database_name']: raise CommandError('Connected database identity mismatch.')
        actor=get_user_model().objects.get(username=options['approved_by'])
        require_staff(actor,'publish_dic_timetables')
        with transaction.atomic():
            edition=CampEdition.objects.select_for_update().get(pk=options['edition'])
            expected={r['source_key']:r for r in data['entries']}
            rows=list(TimetableEntry.objects.select_for_update().filter(edition=edition))
            if len(rows)!=len(expected) or {r.source_key for r in rows}!=set(expected):
                raise CommandError('Edition data differs from the reviewed seed. Review it in Admin; nothing published.')
            for row in rows:
                for key,value in expected[row.source_key].items():
                    if getattr(row,key)!=value: raise CommandError('Staff-edited or outdated data requires separate Admin review; nothing published.')
            if not DICAdminAuditEvent.objects.filter(action='timetable_source_imported',target_type='CampEdition',target_id=str(edition.pk),details__seed_sha256=checksum).exists():
                raise CommandError('Matching reviewed draft import receipt is required.')
            count=0
            for kind in ('activities','food'):
                drafts=TimetableEntry.objects.filter(edition=edition,timetable_type=kind,status='draft')
                if drafts.exists(): count+=publish_days(actor,drafts,True)
        self.stdout.write(f'{count} entries published. Already published rows are unchanged; no entries created.')
