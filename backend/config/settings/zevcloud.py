"""Full native application. No container gateway, Nginx or Supervisor imports."""
import os
from config.native_defaults import configure

configure(os.environ)
from .production import *

DAWANA_WEBSITE_ONLY = False
ZEV_PROXY_HEADERS_VERIFIED = env.bool('ZEV_PROXY_HEADERS_VERIFIED', default=False)
if not ZEV_PROXY_HEADERS_VERIFIED:
    raise ImproperlyConfigured('Confirm managed ingress isolation and sanitized scheme/client forwarding headers before setting ZEV_PROXY_HEADERS_VERIFIED=true.')
if env.bool('DAWANA_WEBSITE_ONLY', default=False):
    raise ImproperlyConfigured('The native deployment is the full application; remove the legacy website-only override.')
# Standard Django HTTPS contract, enabled only after the explicit provider check.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
MIDDLEWARE = ['config.native_security.ManagedHttpsMiddleware', *[
    item for item in MIDDLEWARE if item not in (
        'config.request_security.TrustedGatewayMiddleware',
        'config.request_security.WebsiteOnlyMiddleware')]]
ROOT_URLCONF = 'config.native_urls'
FRONTEND_ROOT = BASE_DIR.parent / 'dawana-platform/dist'
from config.spa import validate_frontend
validate_frontend(FRONTEND_ROOT)
WHITENOISE_ROOT = FRONTEND_ROOT
WHITENOISE_MAX_AGE = 0
WHITENOISE_ADD_HEADERS_FUNCTION = 'config.spa.static_headers'
DIC_WORKER_HEARTBEAT_CACHE = True
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
