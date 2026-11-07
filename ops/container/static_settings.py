"""Build-only static collection. No application models, dotenv or database."""
from pathlib import Path
from importlib.util import find_spec

SECRET_KEY = 'public-static-collection-only-not-an-application-secret'
INSTALLED_APPS = ['django.contrib.staticfiles']
STATIC_URL = '/static/'
STATIC_ROOT = '/app/backend/staticfiles'
STATICFILES_DIRS = [
    '/app/dawana-platform/public',
    '/app/backend/dic/static',
    str(Path(find_spec('django').origin).parent / 'contrib/admin/static'),
]
STORAGES = {'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DATABASES = {}
