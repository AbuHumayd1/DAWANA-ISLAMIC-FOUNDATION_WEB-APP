"""Authenticated PostgreSQL TLS only; no provider-specific downgrade."""
from django.core.exceptions import ImproperlyConfigured


def validate_database_tls(target, host, mode='verify-full'):
    if (target not in ('render', 'self-managed') or not isinstance(host, str) or not host
            or any(char.isspace() or char in '/\\,' for char in host)):
        raise ImproperlyConfigured('Configure a supported deployment target and PostgreSQL hostname.')
    if mode != 'verify-full':
        raise ImproperlyConfigured(
            'PostgreSQL requires DB_SSLMODE=verify-full with a trusted certificate and matching hostname. '
            'Render internal endpoints without authenticated TLS are unsupported; use a verified external endpoint.')
