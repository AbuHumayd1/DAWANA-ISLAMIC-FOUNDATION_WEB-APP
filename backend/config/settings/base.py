from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured
from corsheaders.defaults import default_headers


BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    DB_CONN_MAX_AGE=(int, 60),
    PAYSTACK_HTTP_TIMEOUT_SECONDS=(int, 10),
    DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS=(int, 8),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default=(
        ["http://localhost:5173", "http://127.0.0.1:5173"]
        if DEBUG
        else []
    ),
)
CORS_ALLOW_CREDENTIALS = False
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
PAYSTACK_MODE = env("PAYSTACK_MODE", default="test")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_CALLBACK_URL = env("PAYSTACK_CALLBACK_URL", default="")
PAYSTACK_HTTP_TIMEOUT_SECONDS = env.int("PAYSTACK_HTTP_TIMEOUT_SECONDS")
DIC_EMAIL_RECOVERY_ENABLED = env.bool("DIC_EMAIL_RECOVERY_ENABLED", default=False)
DIC_RECOVERY_DELIVERY_WORKER_ENABLED = env.bool(
    "DIC_RECOVERY_DELIVERY_WORKER_ENABLED",
    default=False,
)
DIC_RECOVERY_ENCRYPTION_KEY = env(
    "DIC_RECOVERY_ENCRYPTION_KEY",
    default="",
)
DIC_SMS_RECOVERY_ADAPTER = env("DIC_SMS_RECOVERY_ADAPTER", default="")
DIC_WHATSAPP_ACCESS_TOKEN = env("DIC_WHATSAPP_ACCESS_TOKEN", default="")
DIC_WHATSAPP_PHONE_NUMBER_ID = env("DIC_WHATSAPP_PHONE_NUMBER_ID", default="")
DIC_WHATSAPP_API_VERSION = env("DIC_WHATSAPP_API_VERSION", default="v23.0")
DIC_WHATSAPP_OTP_TEMPLATE = env("DIC_WHATSAPP_OTP_TEMPLATE", default="")
DIC_WHATSAPP_OTP_LANGUAGE = env("DIC_WHATSAPP_OTP_LANGUAGE", default="en")
DIC_WHATSAPP_SUPPORT_NUMBER = env("DIC_WHATSAPP_SUPPORT_NUMBER", default="")
DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS = env.int(
    "DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS"
)
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="")
if not 1 <= DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS <= 30:
    raise ImproperlyConfigured(
        "DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS must be between 1 and 30."
    )
EMAIL_TIMEOUT = DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "accounts.apps.AccountsConfig",
    "dic.apps.DicConfig",
    "health.apps.HealthConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_name = env("DB_NAME")
test_database_name = env("DB_TEST_NAME", default=f"test_{database_name}")
if test_database_name == database_name:
    raise ImproperlyConfigured(
        "DB_TEST_NAME must be different from DB_NAME to protect development data."
    )
if not test_database_name.startswith("test_"):
    raise ImproperlyConfigured("DB_TEST_NAME must start with 'test_'.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE"),
        "TEST": {
            "NAME": test_database_name,
        },
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "dic_registration_options": "300/hour",
        "dic_registration_create": "100/hour",
        "dic_order_retrieve": "300/hour",
        "dic_payment_initiate": "20/hour",
        "dic_payment_verify": "60/hour",
        "dic_paystack_webhook": "600/minute",
        "dic_recovery_channels": "60/hour",
        "dic_recovery_request": "30/hour",
        "dic_recovery_verify": "30/hour",
        "dic_recovery_orders": "60/hour",
        "dic_recovery_restore": "30/hour",
    },
}
