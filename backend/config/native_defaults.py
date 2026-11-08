"""Only public defaults; never generates secrets or enables live payments."""
import re
from urllib.parse import urlsplit


def configure(env):
    host = env.get('PUBLIC_HOST', '')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host) or '.' not in host:
        raise ValueError('Set PUBLIC_HOST to one exact public hostname without scheme or path.')
    frontend = env.get('FRONTEND_ORIGIN', '')
    try:
        origin = urlsplit(frontend)
        valid = (origin.scheme == 'https' and origin.hostname and not origin.username
                 and not origin.password and origin.port in (None, 443)
                 and not origin.path and not origin.query and not origin.fragment
                 and not any(char.isspace() for char in frontend) and '*' not in frontend
                 and re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', origin.hostname)
                 and origin.netloc == origin.hostname)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Set FRONTEND_ORIGIN to one exact HTTPS origin without path or trailing slash.')
    # Derived for this standalone API, never widen credentialed access via stale
    # container-era DJANGO_* host/origin overrides.
    env['DJANGO_ALLOWED_HOSTS'] = host
    env['DJANGO_CSRF_TRUSTED_ORIGINS'] = frontend
    env['DJANGO_CORS_ALLOWED_ORIGINS'] = frontend
    env['DJANGO_DEPLOYMENT_TARGET'] = 'managed'
    env['DJANGO_DEBUG'] = 'false'
    defaults = {
        'DAWANA_WEBSITE_ONLY': 'false',
        'DIC_PORTAL_ACCOUNTS_ENABLED': 'true',
        'DIC_BACKGROUND_WORKER_ENABLED': 'true',
        'DIC_EMAIL_RECOVERY_ENABLED': 'true',
        'DIC_RECOVERY_DELIVERY_WORKER_ENABLED': 'true',
        'DIC_PORTAL_EMAIL_VERIFY_URL': frontend + '/dic/participant',
        'DIC_PORTAL_FRONTEND_URL': frontend + '/dic/participant',
        'PAYSTACK_CALLBACK_URL': frontend + '/dic/register/payment-return',
        'EMAIL_BACKEND': 'config.https_email.EmailBackend',
        'DB_SSLMODE': 'verify-full',
        'PAYSTACK_MODE': 'test', 'PAYSTACK_LIVE_ENABLED': 'false',
    }
    for name, value in defaults.items():
        env.setdefault(name, value)
    return env
