"""Container-owned defaults. No I/O, secrets output or provider assumptions."""
import os
from urllib.parse import urlsplit, parse_qs
from startup_errors import StartupError


def boolean(value, name):
    value = value.strip().lower()
    if value in ('true', '1', 'yes', 'on'):
        return 'true'
    if value in ('false', '0', 'no', 'off'):
        return 'false'
    raise StartupError('CFG_BOOLEAN_' + name, 'Use a valid true/false value for ' + name + '.')


def csv(value):
    return list(dict.fromkeys(part.strip() for part in value.split(',') if part.strip()))


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
        'DJANGO_DEBUG': 'false',
    }
    for name, value in fixed.items():
        supplied = env.get(name, value)
        if name in ('DJANGO_TRUST_PROXY_HTTPS', 'DJANGO_DEBUG'):
            supplied = boolean(supplied, name)
        elif name in ('DJANGO_ALLOWED_HOSTS', 'DJANGO_CSRF_TRUSTED_ORIGINS', 'DJANGO_CORS_ALLOWED_ORIGINS'):
            values = csv(supplied)
            allowed = [value] if value else []
            if name == 'DJANGO_CORS_ALLOWED_ORIGINS' and values == ['https://' + host]:
                value = 'https://' + host  # Existing entrypoint already permits this safe origin.
            elif values != allowed:
                raise StartupError('CFG_CONFLICT_' + name,
                    'Remove ' + name + ' to derive the single PUBLIC_HOST policy, or supply its matching exact value.')
            supplied = value
        elif name == 'DAWANA_TRUSTED_GATEWAYS':
            supplied = ','.join(csv(supplied))
        if supplied != value:
            raise StartupError('CFG_CONFLICT_' + name, 'Remove the conflicting ' + name + ' override; the container derives its secure value.')
        env[name] = value
    env.setdefault('GATEWAY_TLS_MODE', 'trusted-edge')
    env.setdefault('DAWANA_WEBSITE_ONLY', 'true')
    website = boolean(env['DAWANA_WEBSITE_ONLY'], 'DAWANA_WEBSITE_ONLY')
    env['DAWANA_WEBSITE_ONLY'] = website
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
            supplied = env.get(name, value)
            if value == 'false':
                supplied = boolean(supplied, name)
            if supplied != value:
                raise StartupError('CFG_WEBSITE_ONLY_' + name,
                    'Website-only mode requires ' + name + ' disabled or absent; remove its conflicting override.')
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
        env['DIC_BACKGROUND_WORKER_ENABLED'] = boolean(env['DIC_BACKGROUND_WORKER_ENABLED'], 'DIC_BACKGROUND_WORKER_ENABLED')
    env.setdefault('DIC_BACKGROUND_WORKER_ENABLED', 'false')
    return env


def validate_inputs(env):
    """Preflight local configuration only. Never connect or print supplied values."""
    secret = env.get('DJANGO_SECRET_KEY', '')
    if len(secret) < 50 or secret.startswith('django-insecure-'):
        raise StartupError('CFG_SECRET_KEY', 'Set an independent DJANGO_SECRET_KEY of at least 50 characters.')
    if env.get('DATABASE_URL'):
        try:
            parsed = urlsplit(env['DATABASE_URL'])
            valid = (parsed.scheme in ('postgres', 'postgresql', 'psql', 'pgsql')
                     and bool(parsed.hostname) and bool(parsed.path.strip('/'))
                     and parsed.port != 0 and not parsed.fragment)
            options = parse_qs(parsed.query, keep_blank_values=True)
        except ValueError:
            valid, options = False, {}
        if not valid:
            raise StartupError('CFG_DATABASE_URL', 'Supply a valid PostgreSQL DATABASE_URL, or remove it and use the existing DB_* fields.')
        if 'sslmode' in options and options['sslmode'] != ['verify-full']:
            raise StartupError('CFG_DATABASE_URL_TLS', 'Remove the conflicting DATABASE_URL sslmode option or set it to verify-full.')
        if env.get('DB_SSLROOTCERT') and 'sslrootcert' in options and options['sslrootcert'] != [env['DB_SSLROOTCERT']]:
            raise StartupError('CFG_DATABASE_CA_CONFLICT', 'Use one matching CA file configuration in DB_SSLROOTCERT and DATABASE_URL.')
        ca = env.get('DB_SSLROOTCERT') or (options.get('sslrootcert') or [''])[0]
    else:
        for name in ('DB_HOST', 'DB_NAME', 'DB_USER'):
            if not env.get(name, '').strip():
                raise StartupError('CFG_MISSING_' + name, 'Keep the existing ' + name + ', or configure DATABASE_URL instead.')
        port = env.get('DB_PORT', '5432')
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise StartupError('CFG_DB_PORT', 'Set DB_PORT to the provider PostgreSQL port.')
        ca = env.get('DB_SSLROOTCERT', '')
    if ca and not (os.path.isfile(ca) and os.access(ca, os.R_OK)):
        raise StartupError('CFG_DATABASE_CA_FILE', 'Mount the trusted PostgreSQL CA file readably for UID 10001; DB_SSLROOTCERT is a file path, not PEM text.')
