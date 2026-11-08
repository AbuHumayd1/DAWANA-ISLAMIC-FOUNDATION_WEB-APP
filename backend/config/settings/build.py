"""Static collection only; never load application models, dotenv or databases."""
from pathlib import Path
from importlib.util import find_spec

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = 'public-static-build-only-not-an-application-secret'
INSTALLED_APPS = ['django.contrib.staticfiles']
DATABASES = {}
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR.parent / 'dawana-platform/public', BASE_DIR / 'dic/static',
    str(Path(find_spec('django').origin).parent / 'contrib/admin/static')]
STORAGES = {'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
