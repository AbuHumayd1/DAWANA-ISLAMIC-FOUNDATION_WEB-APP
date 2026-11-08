from .base import *
import os


DEBUG = False
# Public launch is independent of the unfinished registration rollout.
DAWANA_WEBSITE_ONLY = env.bool('DAWANA_WEBSITE_ONLY', default=True)
# Legacy staging imports these HTTPS settings; retain its existing storage path.
DIC_PRODUCTION_STORAGE = os.environ.get('DJANGO_SETTINGS_MODULE') != 'config.settings.staging'
if DIC_PRODUCTION_STORAGE and DAWANA_WEBSITE_ONLY and (PAYSTACK_MODE != 'test' or PAYSTACK_LIVE_ENABLED or PAYSTACK_SECRET_KEY):
    raise ImproperlyConfigured('Website-only launch requires payments disabled and no Paystack key.')
DJANGO_DEPLOYMENT_TARGET = env('DJANGO_DEPLOYMENT_TARGET', default='self-managed')
if DJANGO_DEPLOYMENT_TARGET not in ('self-managed', 'render', 'managed'):
    raise ImproperlyConfigured('Unsupported production deployment target.')
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int('DJANGO_HSTS_SECONDS', default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('DJANGO_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD = env.bool('DJANGO_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Preparation only: no live payments or registration release is implied.
database_options = DATABASES['default'].setdefault('OPTIONS', {})
database_options['sslmode'] = env('DB_SSLMODE', default='verify-full')
if env('DB_SSLROOTCERT', default=''):
    database_options['sslrootcert'] = env('DB_SSLROOTCERT')
from config.deployment_security import validate_database_tls
validate_database_tls(DJANGO_DEPLOYMENT_TARGET, DATABASES['default'].get('HOST'),
    database_options['sslmode'])
if env.bool('DJANGO_TRUST_PROXY_HTTPS', default=False):
    # Enable only behind a proxy that strips incoming forwarded headers.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if DIC_PRODUCTION_STORAGE and DIC_MEMORY_STORAGE == 's3':
    from types import SimpleNamespace
    from dic.storage_configuration import production_storage
    _storage_config = SimpleNamespace(**globals())
    _media_config = production_storage(_storage_config, 'media')
    _private_config = production_storage(_storage_config, 'private')
    if _media_config['aws_access_key_id'] == _private_config['aws_access_key_id']:
        raise ImproperlyConfigured('Production media and participant storage require independent credentials.')
    del _storage_config, _media_config, _private_config
MIDDLEWARE = [*MIDDLEWARE]
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
if DIC_PRODUCTION_STORAGE:
    MIDDLEWARE.insert(0, 'config.request_security.WebsiteOnlyMiddleware')
    MIDDLEWARE.insert(0, 'config.request_security.TrustedGatewayMiddleware')
    MIDDLEWARE.append('config.request_security.AdminLoginThrottleMiddleware')
# Never trust an arbitrary X-Forwarded-For chain. A verified immediate gateway
# must replace X-Dawana-Client-IP and strip client-supplied forwarding headers.
DAWANA_TRUSTED_GATEWAYS = env.list('DAWANA_TRUSTED_GATEWAYS', default=[])
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 0}
STATIC_URL = '/static/'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
# Configure this table through the separately approved release plan; never create
# it automatically at startup. Shared cache is needed for multi-worker throttles.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
    'LOCATION': 'dawana_release_cache', 'KEY_PREFIX': 'dawana-production'}}
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'filters': {'request_privacy': {'()': 'config.staging_logging.RequestPrivacyFilter'}},
    'handlers': {'private_requests': {'class': 'logging.StreamHandler', 'filters': ['request_privacy']}},
    'loggers': {name: {'handlers': ['private_requests'], 'level': 'WARNING', 'propagate': False}
        for name in ('django.request','django.security')},
}
from config.release_security import validate_production
from django.conf.global_settings import PASSWORD_HASHERS
validate_production(globals())
