from .base import *


DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Preparation only: no live payments or registration release is implied.
DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'
MIDDLEWARE = [*MIDDLEWARE]
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
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
