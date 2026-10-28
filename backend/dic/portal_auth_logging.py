"""Redact single-use OAuth codes in Django development/request logs."""
import logging


class OAuthCallbackFilter(logging.Filter):
    def filter(self, record):
        if '/participant/auth/google/callback/' in record.getMessage() or '/participant/auth/google/callback/' in getattr(getattr(record, 'request', None), 'path', ''):
            record.msg = 'Participant OAuth callback [query and exception redacted]'
            record.args = (); record.exc_info = None; record.exc_text = None
        return True


def install():
    for name in ('django.server', 'django.request'):
        logger = logging.getLogger(name)
        if not any(isinstance(item, OAuthCallbackFilter) for item in logger.filters):
            logger.addFilter(OAuthCallbackFilter())
