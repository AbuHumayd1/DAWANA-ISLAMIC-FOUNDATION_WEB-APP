"""Authenticated PostgreSQL TLS only; no provider-specific downgrade."""
from django.core.exceptions import ImproperlyConfigured


def validate_database_tls(target, host, mode='verify-full'):
    if (target not in ('render', 'self-managed', 'managed') or not isinstance(host, str) or not host
            or any(char.isspace() or char in '/\\,' for char in host)):
        raise ImproperlyConfigured('Configure a supported deployment target and PostgreSQL hostname.')
    if mode != 'verify-full':
        raise ImproperlyConfigured(
            'PostgreSQL requires DB_SSLMODE=verify-full with a trusted certificate and matching hostname. '
            'Render internal endpoints without authenticated TLS are unsupported; use a verified external endpoint.')


def application_bind(environ):
    """Explicit managed ingress; loopback remains the self-managed default."""
    target = environ.get('DJANGO_DEPLOYMENT_TARGET', 'self-managed')
    if target not in ('self-managed', 'render', 'managed'):
        raise ValueError('Unsupported deployment target.')
    host = environ.get('DJANGO_BIND_ADDRESS', '0.0.0.0' if target == 'render' else '127.0.0.1')
    if host not in ('127.0.0.1', '0.0.0.0'):
        raise ValueError('Bind address must be explicitly loopback or IPv4 wildcard.')
    if target == 'managed' and 'DJANGO_BIND_ADDRESS' not in environ:
        raise ValueError('Managed ingress requires an explicitly approved bind address.')
    if target == 'self-managed' and host != '127.0.0.1':
        raise ValueError('Self-managed application ports must remain loopback-only.')
    port = str(environ.get('DJANGO_BIND_PORT', environ.get('PORT', '10000') if target != 'self-managed' else '10000'))
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError('Invalid HTTP port.')
    return f'{host}:{int(port)}'
