"""Read-only launch gate. Never migrates, seeds, sends mail or calls Paystack."""
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from dic.housing_service import permitted, require_automation
from dic.models import CampEdition
from dic.recovery import channel_available
from dic.registration_accounts import verification_url


class Command(BaseCommand):
    help = 'Check schema, cache table, edition, housing, actor and delivery settings without mutations.'

    def add_arguments(self, parser):
        parser.add_argument('--require-live', action='store_true')

    def handle(self, *args, **options):
        try:
            if settings.DAWANA_WEBSITE_ONLY or not settings.DIC_BACKGROUND_WORKER_ENABLED:
                raise ValueError('Full application and background processing must be enabled.')
            if not settings.DIC_PORTAL_ACCOUNTS_ENABLED or not channel_available('email'):
                raise ValueError('Accounts and verified email recovery configuration are required.')
            verification_url()
            if settings.DATABASES['default'].get('OPTIONS', {}).get('sslmode') != 'verify-full':
                raise ValueError('Authenticated PostgreSQL TLS is required.')
            ca = settings.DATABASES['default'].get('OPTIONS', {}).get('sslrootcert')
            if ca and not Path(ca).is_file():
                raise ValueError('Configured PostgreSQL CA file is not available.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
                row = cursor.fetchone()
            if not row or row[0] is not True:
                raise ValueError('PostgreSQL connection is not using TLS.')
            executor = MigrationExecutor(connection)
            if executor.loader.detect_conflicts() or executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise ValueError('Pending/conflicting schema requires a separately approved release.')
            if settings.CACHES['default']['LOCATION'] not in connection.introspection.table_names():
                raise ValueError('Shared cache table is missing.')
            actor = get_user_model().objects.get(pk=settings.DIC_AUTOMATION_ACTOR_ID)
            for permission in ('can_process_housing_queue', 'can_allocate_participants', 'can_approve_housing_guardians'):
                permitted(actor, permission)
            editions = list(CampEdition.objects.filter(is_active=True))
            if len(editions) != 1 or editions[0].pricing_configuration_errors():
                raise ValueError('One active edition with complete approved pricing is required.')
            require_automation(editions[0])
            from dic.views import _registration_is_open
            from django.utils import timezone
            if not _registration_is_open(editions[0], timezone.localdate()):
                raise ValueError('Approved registration dates/status are not open.')
            if options['require_live']:
                from dic.payments import PaystackClient
                if settings.PAYSTACK_MODE != 'live' or not settings.PAYSTACK_LIVE_ENABLED:
                    raise ValueError('Live collection is not separately enabled.')
                PaystackClient()  # Configuration only; no provider request.
        except Exception:
            # Provider/DB exceptions may contain credentials. Do not interpolate them.
            raise CommandError('Launch checks failed. Review schema/cache, TLS, edition/housing, actor and delivery configuration; no changes made.') from None
        self.stdout.write('PASS: read-only launch configuration checks. Ingress, email delivery and payment acceptance still require external verification.')
