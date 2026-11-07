"""Synthetic GitHub Actions settings. Never import base or read dotenv files."""
import ast
import base64
import os
import re
from pathlib import Path
from corsheaders.defaults import default_headers

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('DAWANA_CI_ACCEPTANCE') != '1':
    raise RuntimeError('CI settings are restricted to the ephemeral acceptance job.')

BASE_DIR = Path(__file__).resolve().parents[2]
_name = os.environ.get('DAWANA_CI_DATABASE', '')
if not re.fullmatch(r'test_dic_(?:core|tutor|movement|assistance)_[0-9]{14}_[a-f0-9]{8}', _name):
    raise RuntimeError('A unique CI-only test database name is required.')
_port = int(os.environ['DAWANA_CI_PG_PORT'])
if not 1 <= _port <= 65535:
    raise RuntimeError('Invalid ephemeral PostgreSQL port.')

# Reuse declarative app/middleware/policy lists without executing base.py, whose
# normal environment loader is deliberately excluded from this test environment.
_wanted = {'INSTALLED_APPS', 'MIDDLEWARE', 'REST_FRAMEWORK', 'AUTH_PASSWORD_VALIDATORS'}
for _node in ast.parse((BASE_DIR / 'config/settings/base.py').read_text(encoding='utf-8')).body:
    if isinstance(_node, ast.Assign) and len(_node.targets) == 1 and isinstance(_node.targets[0], ast.Name):
        if _node.targets[0].id in _wanted:
            globals()[_node.targets[0].id] = ast.literal_eval(_node.value)
if not _wanted <= globals().keys():
    raise RuntimeError('CI could not load the project declaration lists.')

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1', 'PORT': str(_port),
    'NAME': 'postgres', 'USER': 'dawana_ci', 'PASSWORD': 'ci-ephemeral-only',
    'CONN_MAX_AGE': 0, 'OPTIONS': {'sslmode': 'disable', 'connect_timeout': 10},
    'TEST': {'NAME': _name, 'TEMPLATE': 'template0'},
}}
# sslmode=disable is confined to the job-local disposable service. Production
# settings and authenticated TLS validation are not imported or modified.
SECRET_KEY = 'synthetic-ci-only-' + 'x' * 64
DEBUG = True
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
ROOT_URLCONF = 'config.urls'
AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True
LANGUAGE_CODE = 'en-gb'
USE_I18N = True
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True,
    'DIRS': [BASE_DIR / 'dic/templates'],
    'OPTIONS': {'context_processors': ['django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR.parent / 'dawana-platform/public']
STATIC_ROOT = Path(os.environ['RUNNER_TEMP']) / 'dawana-ci-static'
MEDIA_ROOT = Path(os.environ['RUNNER_TEMP']) / 'dawana-ci-media'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': _name}}
# Use the real default password hashers; do not alter production validation.
CORS_ALLOWED_ORIGINS = ['https://portal.example.test']
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGIN_REGEXES = []
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, 'idempotency-key', 'x-donation-token')
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
CORS_URLS_REGEX = r'^/api/.*$'
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

PAYSTACK_MODE = 'test'
PAYSTACK_LIVE_ENABLED = False
PAYSTACK_SECRET_KEY = 'sk_test_synthetic_ci_only'
PAYSTACK_WEBHOOK_SECRET = ''
PAYSTACK_CALLBACK_URL = 'https://portal.example.test/dic/register/payment-return'
PAYSTACK_HTTP_TIMEOUT_SECONDS = 10
DIC_PORTAL_ACCOUNTS_ENABLED = True
DIC_PORTAL_EMAIL_VERIFY_URL = 'https://portal.example.test/dic/participant'
DIC_PORTAL_FRONTEND_URL = 'https://portal.example.test/dic/participant'
DIC_GOOGLE_CLIENT_ID = DIC_GOOGLE_CLIENT_SECRET = DIC_GOOGLE_REDIRECT_URI = ''
DIC_EMAIL_RECOVERY_ENABLED = DIC_RECOVERY_DELIVERY_WORKER_ENABLED = False
DIC_RECOVERY_ENCRYPTION_KEY = base64.urlsafe_b64encode(b'\0' * 32).decode('ascii')
DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS = 8
DIC_SMS_RECOVERY_ADAPTER = ''
DIC_WHATSAPP_ACCESS_TOKEN = DIC_WHATSAPP_PHONE_NUMBER_ID = DIC_WHATSAPP_OTP_TEMPLATE = ''
DIC_WHATSAPP_API_VERSION = 'v23.0'
DIC_WHATSAPP_OTP_LANGUAGE = 'en'
DIC_WHATSAPP_SUPPORT_NUMBER = ''
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST = ''
EMAIL_PORT = 587
EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_TIMEOUT = 8
DEFAULT_FROM_EMAIL = 'sender@example.test'
DIC_MEMORY_STORAGE = 'disabled'
DIC_MEMORY_S3_BUCKET = DIC_MEMORY_S3_ENDPOINT = ''
DIC_MEMORY_S3_REGION = 'auto'
DIC_PRODUCTION_STORAGE = DIC_PORTRAIT_CUTOVER_VERIFIED = False
for _prefix in ('DIC_MEDIA', 'DIC_PRIVATE'):
    for _suffix in ('S3_BUCKET', 'S3_ENDPOINT', 'S3_REGION', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY'):
        globals()[_prefix + '_' + _suffix] = ''
DIC_VIDEO_APPROVED_PROVIDERS = ['youtube', 'vimeo']
DIC_FFPROBE_BINARY = 'ffprobe'
DIC_OFFICIAL_LOGO_URL = ''
DIC_ASSISTED_BOOKING_ENABLED = False
DIC_FEEDBACK_PRIVACY_KEY = 'synthetic-ci-feedback-only'
FOUNDATION_DONATIONS_ENABLED = FOUNDATION_CONTACT_FORM_ENABLED = FOUNDATION_CONTACT_VERIFIED = False
FOUNDATION_DONATION_CURRENCY = 'NGN'
FOUNDATION_DONATION_MIN_NGN = '0.01'
FOUNDATION_DONATION_MAX_NGN = '92233720368547758.07'
FOUNDATION_CONTACT_EMAIL = FOUNDATION_CONTACT_PHONE = FOUNDATION_CONTACT_WHATSAPP = FOUNDATION_CONTACT_ADDRESS = ''
