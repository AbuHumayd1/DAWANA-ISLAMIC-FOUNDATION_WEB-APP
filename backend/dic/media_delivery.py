"""Sanitized pre-response failures; storage keys and provider errors stay private."""
from functools import wraps
import logging
from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import HttpResponse


logger = logging.getLogger(__name__)


class PortraitUnavailable(Exception):
    """A referenced production portrait must not silently become a blank card."""


def media_headers(response, *, public=False):
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cross-Origin-Resource-Policy'] = 'cross-origin' if public else 'same-origin'
    return response


def media_chunks(body, length):
    """Headers may already be sent: log a fixed message and terminate on failure."""
    remaining = length
    try:
        while remaining:
            chunk = body.read(min(64 * 1024, remaining))
            if not chunk:
                raise OSError('Incomplete media stream')
            remaining -= len(chunk)
            yield chunk
    except (BotoCoreError, ClientError, OSError, ValidationError):
        logger.warning('Media stream terminated before completion.')
    finally:
        try:
            body.close()
        except (BotoCoreError, ClientError, OSError):
            logger.warning('Media stream close failed.')


def safe_media(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except FileNotFoundError:
            response = HttpResponse('Media unavailable.', status=404)
        except ClientError as error:
            missing = str(error.response.get('Error', {}).get('Code', '')) in ('404', 'NoSuchKey', 'NotFound')
            response = HttpResponse('Media unavailable.', status=404 if missing else 503)
        except (BotoCoreError, OSError, ImproperlyConfigured, ValidationError, PortraitUnavailable):
            response = HttpResponse('Media temporarily unavailable.', status=503)
        return media_headers(response)
    return wrapped
