from django.db import connection, DatabaseError
from django.conf import settings
from pathlib import Path
from time import time
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            if getattr(settings, 'DIC_BACKGROUND_WORKER_ENABLED', False):
                heartbeat = Path('/run/dawana/worker-heartbeat')
                if not heartbeat.is_file() or time() - heartbeat.stat().st_mtime > 300:
                    return Response({'status': 'unavailable'}, status=503, headers={'Cache-Control': 'no-store'})
        except (DatabaseError, OSError):
            response = Response({"status": "unavailable"}, status=503)
        else:
            response = Response({"status": "ok"})
        response["Cache-Control"] = "no-store"
        return response
