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
CORS_ALLOW_CREDENTIALS = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=CORS_ALLOWED_ORIGINS,
)
PAYSTACK_MODE = env("PAYSTACK_MODE", default="test")
# Set only after an approved original asset is verified; no substitute logo.
DIC_OFFICIAL_LOGO_URL = env("DIC_OFFICIAL_LOGO_URL", default="")
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
        "DIRS": [BASE_DIR / "dic" / "templates"],
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

# Render supplies DATABASE_URL; retain the established DB_* local configuration.
if env("DATABASE_URL", default=""):
    database = env.db_url("DATABASE_URL")
    if database["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("Only PostgreSQL DATABASE_URL values are supported.")
else:
    database = {
        "ENGINE": "django.db.backends.postgresql", "NAME": env("DB_NAME"),
        "USER": env("DB_USER"), "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"), "PORT": env("DB_PORT", default="5432"),
    }
database_name = database["NAME"]
test_database_name = env("DB_TEST_NAME", default=f"test_{database_name}")
if test_database_name == database_name or not test_database_name.startswith("test_"):
    raise ImproperlyConfigured("DB_TEST_NAME must start with 'test_' and differ from the application database.")
database.update(CONN_MAX_AGE=env.int("DB_CONN_MAX_AGE"), CONN_HEALTH_CHECKS=True,
                TEST={"NAME": test_database_name})
DATABASES = {"default": database}

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
STATICFILES_DIRS = [BASE_DIR.parent / "dawana-platform" / "public"]
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
        "dic_ops_login": "10/hour",
        "dic_participant_request": "30/hour",
        "dic_participant_verify": "60/hour",
        "dic_participant_session": "300/hour",
    },
}


# Uploads remain disabled outside development until private object storage is verified.
DIC_MEMORY_STORAGE = env("DIC_MEMORY_STORAGE", default="local" if DEBUG else "disabled")
DIC_MEMORY_S3_BUCKET = env("DIC_MEMORY_S3_BUCKET", default="")
DIC_MEMORY_S3_ENDPOINT = env("DIC_MEMORY_S3_ENDPOINT", default="")
DIC_MEMORY_S3_REGION = env("DIC_MEMORY_S3_REGION", default="us-east-1")

# No providers are enabled on a deployment until explicitly approved/configured.
DIC_VIDEO_APPROVED_PROVIDERS = env.list("DIC_VIDEO_APPROVED_PROVIDERS", default=[])
