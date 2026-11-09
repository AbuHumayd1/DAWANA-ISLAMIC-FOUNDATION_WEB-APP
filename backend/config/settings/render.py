"""Render API/Admin web process; worker readiness is checked separately."""
import os
import ssl
from pathlib import Path

from config.native_defaults import configure

# Reuse the exact host/origin and safe payment defaults without requiring a
# worker or enabling delivery merely because the web service is running.
os.environ.setdefault('DIC_BACKGROUND_WORKER_ENABLED', 'false')
os.environ.setdefault('DIC_EMAIL_RECOVERY_ENABLED', 'false')
os.environ.setdefault('DIC_RECOVERY_DELIVERY_WORKER_ENABLED', 'false')
configure(os.environ)
os.environ['DJANGO_DEPLOYMENT_TARGET'] = 'render'

from .production import *

DAWANA_WEBSITE_ONLY = False
if env.bool('DAWANA_WEBSITE_ONLY', default=False):
    raise ImproperlyConfigured('Render API settings require application mode.')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
MIDDLEWARE = ['config.native_security.ManagedHttpsMiddleware', *[
    item for item in MIDDLEWARE if item not in (
        'config.request_security.TrustedGatewayMiddleware',
        'config.request_security.WebsiteOnlyMiddleware')]]
FRONTEND_ORIGIN = env('FRONTEND_ORIGIN')
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
CORS_EXPOSE_HEADERS = ['Content-Disposition']
from config.spa import static_headers
WHITENOISE_ADD_HEADERS_FUNCTION = static_headers
LOGGING = {**LOGGING, 'filters': {
    'request_privacy': {'()': 'config.render_logging.RenderRequestPrivacyFilter'}},
    'handlers': {**LOGGING['handlers'], 'readiness': {'class': 'logging.StreamHandler'}},
    'loggers': {**LOGGING['loggers'], 'health.views': {
        'handlers': ['readiness'], 'level': 'WARNING', 'propagate': False}}}

# Keep the shared cache for production throttles, but never consult worker or
# delivery readiness in this web service's database probe.
HEALTH_CHECK_WORKERS = False
DIC_WORKER_HEARTBEAT_CACHE = True
if DIC_MEMORY_STORAGE not in ('disabled', 's3'):
    raise ImproperlyConfigured('Render production uploads require approved object storage.')

database = DATABASES['default']
if '.' not in database['HOST']:
    raise ImproperlyConfigured(
        'Render internal PostgreSQL endpoints do not support verify-full. '
        'Use the full external PostgreSQL hostname with a trusted TLS certificate.')
options = database.setdefault('OPTIONS', {})
# libpq otherwise looks for ~/.postgresql/root.crt, not the OS CA bundle.
root_cert = options.get('sslrootcert') or ssl.get_default_verify_paths().cafile
if not root_cert or not Path(root_cert).is_file() or not os.access(root_cert, os.R_OK):
    raise ImproperlyConfigured('Render PostgreSQL requires a readable trusted CA bundle; configure DB_SSLROOTCERT.')
options['sslrootcert'] = root_cert
options.setdefault('connect_timeout', 3)
# production.py enforces verify-full, including rejection of DB_SSLMODE downgrades.
from config.release_security import validate_production
validate_production(globals())
