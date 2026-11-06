"""Pure production storage validation; never contacts a provider or prints values."""
import re
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def production_storage(config, kind):
    prefix = 'DIC_MEDIA' if kind == 'media' else 'DIC_PRIVATE'
    expected = 'dawana-production-media' if kind == 'media' else 'dawana-production-private'
    def value(suffix): return getattr(config, prefix + suffix, '')
    endpoint = value('_S3_ENDPOINT')
    try:
        parsed = urlsplit(endpoint)
        valid = (parsed.scheme == 'https' and bool(re.fullmatch(r'[a-f0-9]{32}\.r2\.cloudflarestorage\.com', parsed.hostname or ''))
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if kind not in ('media', 'private') or value('_S3_BUCKET') != expected or not valid or value('_S3_REGION') != 'auto':
        raise ImproperlyConfigured('Configure the approved production bucket, R2 HTTPS endpoint and auto region.')
    key, secret = value('_S3_ACCESS_KEY_ID'), value('_S3_SECRET_ACCESS_KEY')
    if not key or not secret:
        raise ImproperlyConfigured('Independent backend storage credentials are required.')
    return dict(bucket=expected, endpoint_url=endpoint, region_name='auto',
                aws_access_key_id=key, aws_secret_access_key=secret)
