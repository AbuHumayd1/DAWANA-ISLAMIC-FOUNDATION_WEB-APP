from django.db import connection, DatabaseError
from django.conf import settings
from pathlib import Path
from time import time
import logging
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    check_workers = True
    check_database = True

    def get(self, request):
        try:
            if self.check_database:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            if (self.check_workers and getattr(settings, 'HEALTH_CHECK_WORKERS', True)
                    and getattr(settings, 'DIC_BACKGROUND_WORKER_ENABLED', False)):
                if getattr(settings, 'DIC_WORKER_HEARTBEAT_CACHE', False):
                    from config.worker_health import healthy
                    from dic.recovery import channel_available
                    ready = healthy() and channel_available('email')
                else:
                    heartbeat = Path('/run/dawana/worker-heartbeat')
                    ready = heartbeat.is_file() and time() - heartbeat.stat().st_mtime <= 300
                if not ready:
                    return Response({'status': 'unavailable'}, status=503, headers={'Cache-Control': 'no-store'})
        except (DatabaseError, OSError, ImproperlyConfigured) as exc:
            # Driver messages can contain connection strings. Log only the type.
            logger.warning('Readiness dependency unavailable (%s).', type(exc).__name__)
            response = Response({"status": "unavailable"}, status=503)
        except Exception as exc:
            logger.error('Unexpected readiness failure (%s).', type(exc).__name__)
            response = Response({"status": "unavailable"}, status=503)
        else:
            response = Response({"status": "ok"})
        response["Cache-Control"] = "no-store"
        return response


class WebHealthCheckView(HealthCheckView):
    """Web-process readiness; no database, cache, worker or delivery access."""
    check_workers = False
    check_database = False
