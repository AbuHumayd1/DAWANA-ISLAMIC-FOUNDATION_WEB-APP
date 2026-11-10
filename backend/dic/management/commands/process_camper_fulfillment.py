"""Explicit bounded ID drain; housing stays in process_dic_followups."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from dic.fulfillment import enabled, process, retry
from dic.models import CamperFulfillmentJob


class Command(BaseCommand):
    help = 'Process default-off ID preparation; never allocates houses or verifies payments.'

    def add_arguments(self, parser):
        parser.add_argument('--database-name', required=True)
        parser.add_argument('--approve-writes', action='store_true')
        parser.add_argument('--edition', type=int, required=True)
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--retry-job', type=int)
        parser.add_argument('--actor', type=int)

    def handle(self, *args, **options):
        if not (enabled() and options['approve_writes']
                and options['database_name'] == str(settings.DATABASES['default']['NAME'])
                and settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'
                and not settings.DATABASE_ROUTERS and 1 <= options['limit'] <= 100
                and options['edition'] > 0):
            raise CommandError('Enabled rollout, exact PostgreSQL target, edition and explicit write approval required.')
        if options['retry_job']:
            if not options['actor']:
                raise CommandError('A reviewed ID retry requires an authorized staff actor.')
            from django.contrib.auth import get_user_model
            if not CamperFulfillmentJob.objects.filter(pk=options['retry_job'], order__edition_id=options['edition']).exists():
                raise CommandError('ID job is unavailable in the selected edition.')
            retry(options['retry_job'], get_user_model().objects.get(pk=options['actor']))
            return
        if options['actor']:
            raise CommandError('Actor is accepted only for an explicit reviewed retry.')
        jobs = (CamperFulfillmentJob.objects.filter(state='pending', order__edition_id=options['edition'])
                .filter(Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()))
                .order_by('created_at', 'pk').values_list('pk', flat=True)[:options['limit']])
        incomplete = False
        for job_id in list(jobs):
            try:
                process(job_id)
            except Exception:
                incomplete = True
                self.stderr.write('ID processing incomplete; durable pending work retained. Raw error suppressed.')
        if incomplete:
            raise CommandError('ID processing needs review; housing is managed independently.')
