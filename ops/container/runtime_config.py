"""Container-owned defaults. No I/O, secrets output or provider assumptions."""
def configure(env):
    host = env.get('PUBLIC_HOST', '')
    fixed = {
        'DJANGO_SETTINGS_MODULE': 'config.settings.production',
        'DJANGO_DEPLOYMENT_TARGET': 'self-managed',
        'DJANGO_BIND_ADDRESS': '127.0.0.1', 'DJANGO_BIND_PORT': '10000',
        'DAWANA_TRUSTED_GATEWAYS': '127.0.0.1/32',
        'DJANGO_TRUST_PROXY_HTTPS': 'true',
        'DJANGO_ALLOWED_HOSTS': host,
        'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://' + host,
        'DJANGO_CORS_ALLOWED_ORIGINS': '',
        'DB_SSLMODE': 'verify-full',
    }
    for name, value in fixed.items():
        if name in env and env[name] != value:
            raise ValueError('Conflicting container security setting: ' + name)
        env[name] = value
    env.setdefault('GATEWAY_TLS_MODE', 'trusted-edge')
    env.setdefault('DAWANA_WEBSITE_ONLY', 'true')
    website = env['DAWANA_WEBSITE_ONLY'].lower()
    if website not in ('true', 'false'):
        raise ValueError('DAWANA_WEBSITE_ONLY must be true or false.')
    if website == 'true':
        disabled = {
            'PAYSTACK_MODE': 'test', 'PAYSTACK_LIVE_ENABLED': 'false',
            'PAYSTACK_SECRET_KEY': '', 'PAYSTACK_WEBHOOK_SECRET': '',
            'DIC_PORTAL_ACCOUNTS_ENABLED': 'false',
            'DIC_ASSISTED_BOOKING_ENABLED': 'false',
            'DIC_EMAIL_RECOVERY_ENABLED': 'false',
            'DIC_RECOVERY_DELIVERY_WORKER_ENABLED': 'false',
            'FOUNDATION_DONATIONS_ENABLED': 'false',
            'FOUNDATION_CONTACT_FORM_ENABLED': 'false',
            'DIC_MEMORY_STORAGE': 'disabled',
            'DIC_BACKGROUND_WORKER_ENABLED': 'false',
        }
        for name, value in disabled.items():
            if name in env and env[name] != value:
                raise ValueError('Website-only mode conflicts with: ' + name)
            env[name] = value
    else:
        defaults = {
            'DIC_BACKGROUND_WORKER_ENABLED': 'true',
            'DIC_PORTAL_ACCOUNTS_ENABLED': 'true',
            'DIC_EMAIL_RECOVERY_ENABLED': 'true',
            'DIC_RECOVERY_DELIVERY_WORKER_ENABLED': 'true',
            'DIC_PORTAL_EMAIL_VERIFY_URL': 'https://' + host + '/dic/participant',
            'DIC_PORTAL_FRONTEND_URL': 'https://' + host + '/dic/participant',
            'PAYSTACK_CALLBACK_URL': 'https://' + host + '/dic/register/payment-return',
            'PAYSTACK_MODE': 'test', 'PAYSTACK_LIVE_ENABLED': 'false',
            'DIC_MEMORY_STORAGE': 'disabled', 'EMAIL_BACKEND': 'config.https_email.EmailBackend',
        }
        for name, value in defaults.items():
            env.setdefault(name, value)
        if env['DIC_BACKGROUND_WORKER_ENABLED'] not in ('true', 'false'):
            raise ValueError('DIC_BACKGROUND_WORKER_ENABLED must be true or false.')
    env.setdefault('DIC_BACKGROUND_WORKER_ENABLED', 'false')
    return env
