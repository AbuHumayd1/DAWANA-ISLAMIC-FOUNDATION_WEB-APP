"""Render staging overlay. Reuses production security and the existing domain APIs."""
from urllib.parse import urlsplit
from .production import *


if not env("DATABASE_URL", default=""):
    raise ImproperlyConfigured("Staging requires an explicit PostgreSQL DATABASE_URL.")
if env("STAGING_DATABASE_NAME", default="") != DATABASES["default"]["NAME"]:
    raise ImproperlyConfigured("STAGING_DATABASE_NAME must explicitly match the new staging database.")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Staging requires a unique, strong DJANGO_SECRET_KEY.")
if not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Staging requires exact DJANGO_ALLOWED_HOSTS.")
for origin in [*CORS_ALLOWED_ORIGINS, *CSRF_TRUSTED_ORIGINS]:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or "*" in origin:
        raise ImproperlyConfigured("Staging CORS/CSRF origins must be exact HTTPS origins without trailing slashes.")
if not CORS_ALLOWED_ORIGINS or not set(CORS_ALLOWED_ORIGINS).issubset(CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Allow the staging frontend explicitly in both CORS and CSRF origins.")
if PAYSTACK_MODE != "test" or (PAYSTACK_SECRET_KEY and not PAYSTACK_SECRET_KEY.startswith("sk_test_")):
    raise ImproperlyConfigured("Staging accepts Paystack test mode and sk_test_ keys only.")

# Render terminates TLS and supplies this header. Do not expose this configuration
# behind a proxy that passes client-supplied forwarded headers unchanged.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"
MIDDLEWARE = [*MIDDLEWARE]
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
# Fail closed until existing operations users are explicitly approved. This
# middleware is absent from development/production settings.
STAGING_DIC_TESTER_RESTRICTION_ENABLED = env.bool(
    "STAGING_DIC_TESTER_RESTRICTION_ENABLED", default=True
)
STAGING_DIC_TESTER_USERNAMES = env.list("STAGING_DIC_TESTER_USERNAMES", default=[])
MIDDLEWARE.append("config.staging_tester_access.DICStagingTesterMiddleware")
STATIC_URL = "/static/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Shared persistent throttle cache; created only on the new staging DB by the
# approved migration command. Never create it against the local application DB.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache",
                      "LOCATION": "dawana_staging_cache", "KEY_PREFIX": "dawana-staging"}}
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 1}

# Messaging defaults OFF. Optional test mail may only target explicit .test
# addresses and a separately configured sandbox SMTP sink. SMS/WhatsApp stay OFF.
STAGING_EMAIL_RECIPIENTS = env.list("STAGING_EMAIL_RECIPIENTS", default=[])
DIC_EMAIL_RECOVERY_ENABLED = env.bool("STAGING_EMAIL_ENABLED", default=False)
DIC_RECOVERY_DELIVERY_WORKER_ENABLED = DIC_EMAIL_RECOVERY_ENABLED
DIC_SMS_RECOVERY_ADAPTER = ""
DIC_WHATSAPP_ACCESS_TOKEN = ""
DIC_WHATSAPP_PHONE_NUMBER_ID = ""
DIC_WHATSAPP_OTP_TEMPLATE = ""
EMAIL_BACKEND = "config.staging_email.SandboxEmailBackend"
EMAIL_HOST = env("STAGING_EMAIL_HOST", default="")
EMAIL_PORT = env.int("STAGING_EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("STAGING_EMAIL_USER", default="")
EMAIL_HOST_PASSWORD = env("STAGING_EMAIL_PASSWORD", default="")
DEFAULT_FROM_EMAIL = "dawana-staging@example.test"
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
if DIC_EMAIL_RECOVERY_ENABLED:
    from cryptography.fernet import Fernet
    try:
        Fernet(DIC_RECOVERY_ENCRYPTION_KEY.encode('ascii'))
    except (ValueError, UnicodeError):
        raise ImproperlyConfigured("Sandbox OTP email requires a valid encryption key.") from None
    if not EMAIL_HOST or not STAGING_EMAIL_RECIPIENTS:
        raise ImproperlyConfigured("Sandbox OTP email requires its SMTP sink, .test allowlist and encryption key.")
    if any(not address.lower().endswith(".test") or "@" not in address for address in STAGING_EMAIL_RECIPIENTS):
        raise ImproperlyConfigured("Sandbox recipients must be explicit non-routable .test email addresses.")

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "filters": {"request_privacy": {"()": "config.staging_logging.RequestPrivacyFilter"}},
    "formatters": {"plain": {"format": "{levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "private_requests": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["request_privacy"]},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["private_requests"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["private_requests"], "level": "WARNING", "propagate": False},
    },
}
