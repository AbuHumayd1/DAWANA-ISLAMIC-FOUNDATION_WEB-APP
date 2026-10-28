"""Loopback development diagnostic; no credentials, participant rows or writes."""
import hmac
import os
from django.conf import settings
from django.db import connection
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def local_database_identity(request):
    token = os.environ.get('DAWANA_LOCAL_DIAGNOSTIC_TOKEN', '')
    if (not settings.DEBUG or settings.SETTINGS_MODULE != 'config.settings.development'
            or request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1') or not token
            or not hmac.compare_digest(request.headers.get('X-Dawana-Local-Diagnostic', ''), token)):
        raise Http404
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        name = cursor.fetchone()[0]
    response = JsonResponse({'database': name, 'synthetic': name.startswith('dawana_ids_demo_')})
    response['Cache-Control'] = 'no-store'
    return response
