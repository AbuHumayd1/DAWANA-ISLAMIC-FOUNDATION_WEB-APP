"""Standalone native Django API/Admin; React is independently static-hosted."""
import os
from config.native_defaults import configure

configure(os.environ)
from .production import *

DAWANA_WEBSITE_ONLY = False
if env.bool('DAWANA_WEBSITE_ONLY', default=False):
    raise ImproperlyConfigured('The native deployment is the full application; remove the legacy website-only override.')
# Standard TLS-terminating reverse-proxy deployment. Ingress must replace this
# header and prevent direct bypass; documented release dependency, no ack flag.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
MIDDLEWARE = ['config.native_security.ManagedHttpsMiddleware', *[
    item for item in MIDDLEWARE if item not in (
        'config.request_security.TrustedGatewayMiddleware',
        'config.request_security.WebsiteOnlyMiddleware')]]
ROOT_URLCONF = 'config.urls'
FRONTEND_ORIGIN = env('FRONTEND_ORIGIN')
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CORS_EXPOSE_HEADERS = ['Content-Disposition']
from config.spa import static_headers
WHITENOISE_ADD_HEADERS_FUNCTION = static_headers
DIC_WORKER_HEARTBEAT_CACHE = True
if DIC_MEMORY_STORAGE not in ('disabled', 's3'):
    raise ImproperlyConfigured('Native production uploads require approved object storage; local storage is unsupported.')
if not DIC_PORTAL_ACCOUNTS_ENABLED or not DIC_BACKGROUND_WORKER_ENABLED:
    raise ImproperlyConfigured('Full native operation requires portal accounts and the durable worker service.')
if DIC_AUTOMATION_ACTOR_ID <= 0:
    raise ImproperlyConfigured('Set the existing authorized automation service-user ID.')
from cryptography.fernet import Fernet
try:
    Fernet(DIC_RECOVERY_ENCRYPTION_KEY.encode('ascii'))
except (ValueError, UnicodeError):
    raise ImproperlyConfigured('Set a stable valid recovery Fernet encryption key.') from None
if (not DIC_EMAIL_RECOVERY_ENABLED or not DIC_RECOVERY_DELIVERY_WORKER_ENABLED
        or not DEFAULT_FROM_EMAIL or EMAIL_BACKEND.lower().endswith(('console.emailbackend', 'locmem.emailbackend'))
        or (EMAIL_BACKEND == 'config.https_email.EmailBackend' and not RESEND_API_KEY)):
    raise ImproperlyConfigured('Configure email recovery, its encryption key and an accepted HTTPS email transport.')
