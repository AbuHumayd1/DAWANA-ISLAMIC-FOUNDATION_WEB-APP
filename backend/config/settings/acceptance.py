"""Standalone acceptance settings: no import of base/development and no dotenv."""
import ast
import os
from pathlib import Path
from acceptance_bootstrap.config import AcceptanceConfig
from acceptance_bootstrap.runtime import assert_active
from acceptance_bootstrap.payments import MOCK_SECRET

ACCEPTANCE = AcceptanceConfig.from_env(os.environ)
assert_active(ACCEPTANCE)
BASE_DIR = Path(__file__).resolve().parents[2]
# Reuse only literal app/middleware/policy definitions. Never execute base.py.
_wanted = {'INSTALLED_APPS', 'MIDDLEWARE', 'REST_FRAMEWORK', 'AUTH_PASSWORD_VALIDATORS'}
for _node in ast.parse((BASE_DIR / 'config/settings/base.py').read_text(encoding='utf-8')).body:
    if isinstance(_node, ast.Assign) and len(_node.targets) == 1 and isinstance(_node.targets[0], ast.Name) and _node.targets[0].id in _wanted:
        globals()[_node.targets[0].id] = ast.literal_eval(_node.value)
if not _wanted.issubset(globals()):
    raise RuntimeError('Acceptance literal settings contract changed.')
SECRET_KEY = ACCEPTANCE.secret
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
DATABASES = {'default': dict(ENGINE='acceptance_bootstrap.db_backend', NAME=ACCEPTANCE.database,
    HOST=ACCEPTANCE.host, PORT=str(ACCEPTANCE.port), USER=ACCEPTANCE.app_role,
    PASSWORD=ACCEPTANCE.password, CONN_MAX_AGE=0, OPTIONS={'connect_timeout': 3},
    TEST={'NAME': ACCEPTANCE.database})}
# TEST name is not authorization to run Django's database-creating test runner.
# Every connection is denied by attach_django for this database-free bootstrap.
ROOT_URLCONF = 'config.urls'
AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True
USE_I18N = True
STATIC_URL = '/static/'
TEMPLATES = [dict(BACKEND='django.template.backends.django.DjangoTemplates', APP_DIRS=True,
    OPTIONS={'context_processors': ['django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']})]
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'dic-acceptance'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'acceptance@example.test'
EMAIL_HOST = EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = ''
PAYSTACK_MODE = 'test'
PAYSTACK_SECRET_KEY = MOCK_SECRET
PAYSTACK_CALLBACK_URL = ''
PAYSTACK_HTTP_TIMEOUT_SECONDS = 1
DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS = 1
DIC_RECOVERY_ENCRYPTION_KEY = ''
DIC_EMAIL_RECOVERY_ENABLED = False
DIC_RECOVERY_DELIVERY_WORKER_ENABLED = False
DIC_SMS_RECOVERY_ADAPTER = DIC_WHATSAPP_ACCESS_TOKEN = DIC_WHATSAPP_PHONE_NUMBER_ID = ''
DIC_GOOGLE_CLIENT_ID = DIC_GOOGLE_CLIENT_SECRET = DIC_GOOGLE_REDIRECT_URI = ''
DIC_ASSISTED_BOOKING_ENABLED = False
DIC_PORTAL_ACCOUNTS_ENABLED = True
DIC_PORTAL_EMAIL_VERIFY_URL = 'http://127.0.0.1/dic/participant'
DIC_PORTAL_FRONTEND_URL = 'http://127.0.0.1'
DIC_MEMORY_STORAGE = 'disabled'
DIC_VIDEO_APPROVED_PROVIDERS = []
DIC_FEEDBACK_PRIVACY_KEY = ACCEPTANCE.secret
DIC_OFFICIAL_LOGO_URL = ''
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
