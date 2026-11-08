"""Run bounded existing commands inside the combined container; no broker."""
from io import StringIO
from pathlib import Path
import signal
import threading
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from dic.models import CampEdition


HEARTBEAT = Path('/run/dawana/worker-heartbeat')


def run_cycle():
    # Commands retain their permission, payment-evidence and claim checks.
    options = dict(stdout=StringIO(), stderr=StringIO())
    # Short-lived OTPs take priority over housing and verification email retries.
    call_command('send_dic_recovery_messages', limit=10, **options)
    call_command('send_dic_portal_messages', limit=10, **options)
    for edition_id in CampEdition.objects.filter(is_active=True).values_list('pk', flat=True):
        call_command('process_dic_followups', edition=edition_id,
            actor=settings.DIC_AUTOMATION_ACTOR_ID,
            database_name=str(settings.DATABASES['default']['NAME']), limit=10, **options)
    HEARTBEAT.touch()


class Command(BaseCommand):
    help = 'Run automatic housing, verification and recovery delivery until stopped.'

    def handle(self, *args, **options):
        if (getattr(settings, 'DAWANA_WEBSITE_ONLY', True)
                or not settings.DIC_BACKGROUND_WORKER_ENABLED or settings.DIC_AUTOMATION_ACTOR_ID <= 0):
            raise CommandError('Explicit application mode and automation actor are required.')
        stopped = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        cycles = 0
        # Do not reuse a heartbeat left by a previous process/container restart.
        HEARTBEAT.unlink(missing_ok=True)
        while not stopped.is_set():
            close_old_connections()
            try:
                run_cycle()
                cycles += 1
                if cycles % 120 == 0:
                    call_command('cleanup_dic_recovery', stdout=StringIO(), stderr=StringIO())
                    call_command('cleanup_dic_participant_access', limit=500, stdout=StringIO(), stderr=StringIO())
            except Exception:
                # Never log command arguments, tokens, destinations or DB/provider exceptions.
                self.stderr.write('Background processing cycle failed; retrying. Check launch configuration and schema.')
            finally:
                close_old_connections()
            stopped.wait(15)
