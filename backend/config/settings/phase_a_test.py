"""Synthetic-only in-memory tests. No dotenv, base import or database credentials.

PostgreSQL locking tests still require the existing guarded disposable CI job.
"""
import ast
import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
for node in ast.parse((BASE_DIR / 'config/settings/base.py').read_text(encoding='utf-8')).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {'INSTALLED_APPS', 'MIDDLEWARE', 'REST_FRAMEWORK', 'AUTH_PASSWORD_VALIDATORS'}:
            globals()[node.targets[0].id] = ast.literal_eval(node.value)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
SECRET_KEY = 'synthetic-phase-a-only-' + 'x' * 64
DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
ROOT_URLCONF = 'config.urls'
AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True
LANGUAGE_CODE = 'en-gb'
STATIC_URL = '/static/'
TEMPLATES = [dict(BACKEND='django.template.backends.django.DjangoTemplates', APP_DIRS=True, DIRS=[BASE_DIR / 'dic/templates'],
    OPTIONS={'context_processors': ['django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'config.site_context.public_site']})]
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'phase-a-synthetic'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'sender@example.test'
EMAIL_HOST = EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = ''
RESEND_API_KEY = ''
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_TRUSTED_ORIGINS = ['https://portal.example.test']
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
CORS_ALLOW_CREDENTIALS = True
PAYSTACK_MODE = 'test'
PAYSTACK_LIVE_ENABLED = False
PAYSTACK_SECRET_KEY = 'sk_test_unit_mock'
PAYSTACK_WEBHOOK_SECRET = ''
PAYSTACK_CALLBACK_URL = 'https://portal.example.test/dic/register/payment-return'
PAYSTACK_HTTP_TIMEOUT_SECONDS = 1
DIC_PORTAL_ACCOUNTS_ENABLED = True
DIC_RECOVERY_ENCRYPTION_KEY = base64.urlsafe_b64encode(b'\0' * 32).decode('ascii')
DIC_EMAIL_RECOVERY_ENABLED = DIC_RECOVERY_DELIVERY_WORKER_ENABLED = False
DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS = 1
DIC_PORTAL_FRONTEND_URL = 'https://portal.example.test/dic/participant'
DIC_PORTAL_EMAIL_VERIFY_URL = DIC_PORTAL_FRONTEND_URL
DIC_GOOGLE_CLIENT_ID = DIC_GOOGLE_CLIENT_SECRET = DIC_GOOGLE_REDIRECT_URI = ''
DIC_SMS_RECOVERY_ADAPTER = DIC_WHATSAPP_ACCESS_TOKEN = DIC_WHATSAPP_PHONE_NUMBER_ID = ''
DIC_MEMORY_STORAGE = 'disabled'
DIC_PRODUCTION_STORAGE = DIC_PORTRAIT_CUTOVER_VERIFIED = False
DIC_MEMORY_S3_BUCKET = DIC_MEMORY_S3_ENDPOINT = ''
DIC_MEMORY_S3_REGION = 'auto'
DIC_VIDEO_APPROVED_PROVIDERS = ['youtube', 'vimeo']
DIC_ASSISTED_BOOKING_ENABLED = False
DIC_FEEDBACK_PRIVACY_KEY = SECRET_KEY
DIC_OFFICIAL_LOGO_URL = ''
FOUNDATION_DONATIONS_ENABLED = FOUNDATION_CONTACT_FORM_ENABLED = False
# Tests use Django's fast test hasher; a dedicated test overrides it to PBKDF2.
# Production hashers and staff validators are never changed.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
