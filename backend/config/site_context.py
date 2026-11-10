"""Public return links for split frontend/backend hosting; never request-derived."""
from urllib.parse import urlsplit
from django.conf import settings


def public_site(request):
    candidate = getattr(settings, 'FRONTEND_ORIGIN', '')
    try:
        url = urlsplit(candidate)
        secure = url.scheme == 'https' and url.port in (None, 443)
        local = settings.DEBUG and url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')
        if (secure or local) and url.hostname and not (url.username or url.password or url.query or url.fragment) \
                and url.path in ('', '/') and not any(char.isspace() for char in candidate):
            return {'public_site_url': candidate.rstrip('/') + '/'}
    except (ValueError, TypeError, AttributeError):
        pass
    return {'public_site_url': '/'}
