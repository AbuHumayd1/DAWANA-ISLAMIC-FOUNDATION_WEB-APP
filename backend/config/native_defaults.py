"""Only public defaults; never generates secrets or enables live payments."""
import re


def configure(env):
    host = env.get('PUBLIC_HOST', '')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host) or '.' not in host:
        raise ValueError('Set PUBLIC_HOST to one exact public hostname without scheme or path.')
    defaults = {
        'DJANGO_ALLOWED_HOSTS': host,
        'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://' + host,
        'DJANGO_CORS_ALLOWED_ORIGINS': '',
        'DJANGO_DEPLOYMENT_TARGET': 'managed',
        'DAWANA_WEBSITE_ONLY': 'false',
        'DIC_PORTAL_ACCOUNTS_ENABLED': 'true',
        'DIC_BACKGROUND_WORKER_ENABLED': 'true',
        'DIC_EMAIL_RECOVERY_ENABLED': 'true',
        'DIC_RECOVERY_DELIVERY_WORKER_ENABLED': 'true',
        'DIC_PORTAL_EMAIL_VERIFY_URL': 'https://' + host + '/dic/participant',
        'DIC_PORTAL_FRONTEND_URL': 'https://' + host + '/dic/participant',
        'PAYSTACK_CALLBACK_URL': 'https://' + host + '/dic/register/payment-return',
        'EMAIL_BACKEND': 'config.https_email.EmailBackend',
        'DB_SSLMODE': 'verify-full',
        'PAYSTACK_MODE': 'test', 'PAYSTACK_LIVE_ENABLED': 'false',
    }
    for name, value in defaults.items():
        env.setdefault(name, value)
    return env
