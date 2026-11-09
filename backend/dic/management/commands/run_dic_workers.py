"""Run bounded durable commands as a native worker or rollback container role."""
from io import StringIO
from pathlib import Path
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from dic.models import CampEdition


HEARTBEAT = Path('/run/dawana/worker-heartbeat')


def validate_worker_configuration():
    from dic.recovery import recovery_encryption_configured, channel_available
    from dic.registration_accounts import verification_url
    if not recovery_encryption_configured():
        raise CommandError('Worker requires the existing valid DIC_RECOVERY_ENCRYPTION_KEY; no replacement key was generated.')
    if not channel_available('email'):
        raise CommandError('Worker requires enabled recovery delivery, DEFAULT_FROM_EMAIL and a configured real email backend (RESEND_API_KEY for the default backend).')
    try:
        verification_url()
    except Exception:
        raise CommandError('Worker requires a valid portal email verification URL.') from None


def configured_actor_id():
    actor_id = getattr(settings, 'DIC_AUTOMATION_ACTOR_ID', None)
    # Settings normally parses this as an integer; reject other types rather
    # than coercing booleans, fractions or malformed values into an identity.
    if type(actor_id) is not int or not 0 < actor_id <= 2**63 - 1:
        raise CommandError('Worker automation actor requires a valid positive integer DIC_AUTOMATION_ACTOR_ID.')
    return actor_id


def validate_actor():
    actor_id = configured_actor_id()
    from dic.housing_service import permitted
    try:
        actor = get_user_model().objects.get(pk=actor_id)
        for permission in ('can_process_housing_queue', 'can_allocate_participants', 'can_approve_housing_guardians'):
            permitted(actor, permission)
    except (get_user_model().DoesNotExist, PermissionDenied):
        raise CommandError('Worker automation actor is missing, inactive or lacks required permissions.') from None
    return actor_id


def run_cycle():
    validate_worker_configuration()
    actor_id = validate_actor()
    # Commands retain their permission, payment-evidence and claim checks.
    options = dict(stdout=StringIO(), stderr=StringIO())
    # Short-lived OTPs take priority over housing and verification email retries.
    call_command('send_dic_recovery_messages', limit=10, **options)
    call_command('send_dic_portal_messages', limit=10, **options)
    for edition_id in CampEdition.objects.filter(is_active=True).values_list('pk', flat=True):
        call_command('process_dic_followups', edition=edition_id,
            actor=actor_id,
            database_name=str(settings.DATABASES['default']['NAME']), limit=10, **options)
    if getattr(settings, 'DIC_WORKER_HEARTBEAT_CACHE', False):
        from config.worker_health import beat
        beat()
    else:
        HEARTBEAT.touch()


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health/':
            self.send_error(404)
            return
        from config.worker_health import healthy
        try:
            ready = healthy()
        except Exception:
            ready = False
        finally:
            connections.close_all()  # Health-server threads have no Django request lifecycle.
        body = b'{"status":"ok"}' if ready else b'{"status":"unavailable"}'
        self.send_response(200 if ready else 503)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Command(BaseCommand):
    help = 'Run automatic housing, verification and recovery delivery until stopped.'

    def add_arguments(self, parser):
        parser.add_argument('--health-port', type=int)

    def handle(self, *args, **options):
        if (getattr(settings, 'DAWANA_WEBSITE_ONLY', True)
                or not getattr(settings, 'DIC_BACKGROUND_WORKER_ENABLED', False)):
            raise CommandError('Explicit application mode and automation actor are required.')
        configured_actor_id()  # Reject invalid identities without database access.
        validate_worker_configuration()  # Fail before opening health or claiming any jobs.
        stopped = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        cycles = 0
        server = None
        if options.get('health_port') is not None:
            if not 1 <= options['health_port'] <= 65535:
                raise CommandError('Health port must be a valid service port.')
            server = ThreadingHTTPServer(('0.0.0.0', options['health_port']), HealthHandler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
        if not getattr(settings, 'DIC_WORKER_HEARTBEAT_CACHE', False):
            HEARTBEAT.unlink(missing_ok=True)
        try:
            while not stopped.is_set():
                close_old_connections()
                try:
                    run_cycle()
                    cycles += 1
                    if cycles % 120 == 0:
                        call_command('cleanup_dic_recovery', stdout=StringIO(), stderr=StringIO())
                        call_command('cleanup_dic_participant_access', limit=500, stdout=StringIO(), stderr=StringIO())
                except (CommandError, PermissionDenied, ImproperlyConfigured):
                    raise CommandError('Worker configuration is invalid; review actor permissions and application configuration.') from None
                except Exception:
                    self.stderr.write('Background processing cycle failed; retrying. Check launch configuration and schema.')
                finally:
                    close_old_connections()
                stopped.wait(15)
        finally:
            if server:
                server.shutdown()
                server.server_close()
