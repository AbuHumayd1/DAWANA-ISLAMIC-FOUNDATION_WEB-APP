"""Pure configuration validation; never prints supplied values or connects."""
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def validate_production(config):
    def require(ok,message):
        if not ok: raise ImproperlyConfigured(message)
    require(config.get('DEBUG') is False,'Production DEBUG must be disabled.')
    secret=config.get('SECRET_KEY','')
    require(len(secret)>=50 and not secret.startswith('django-insecure-'),'Production requires a strong independent secret.')
    hosts=config.get('ALLOWED_HOSTS',[])
    require(bool(hosts) and all(host and '*' not in host and not host.startswith('.') and '://' not in host for host in hosts),'Production requires exact allowed hosts.')
    for key in ('CORS_ALLOWED_ORIGINS','CSRF_TRUSTED_ORIGINS'):
        for origin in config.get(key,[]):
            parsed=urlsplit(origin)
            require(parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment and '*' not in origin,'Production origins must be exact HTTPS origins.')
    require(set(config.get('CORS_ALLOWED_ORIGINS',[]))<=set(config.get('CSRF_TRUSTED_ORIGINS',[])),'CORS origins must also be CSRF trusted origins.')
    require(not config.get('CORS_ALLOW_ALL_ORIGINS', False) and not config.get('CORS_ALLOWED_ORIGIN_REGEXES', []),
            'Credentialed CORS requires explicit trusted origins; wildcard and regex origins are unsupported.')
    for key in ('SECURE_SSL_REDIRECT','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE'):
        require(config.get(key) is True,'Production HTTPS and secure cookies are required.')
    mode = config.get('PAYSTACK_MODE')
    require(mode in ('test', 'live'), 'Invalid Paystack mode.')
    if mode == 'live':
        require(config.get('PAYSTACK_LIVE_ENABLED') is True, 'Live Paystack activation has not been approved.')
        require(bool(config.get('PAYSTACK_CALLBACK_URL')), 'Live collection requires an HTTPS callback URL.')
    key=config.get('PAYSTACK_SECRET_KEY','')
    require((not key and mode == 'test') or key.startswith('sk_'+mode+'_'), 'Paystack key and mode must match.')
    if mode == 'live':
        # Runtime client repeats validation; here validate the supplied configuration.
        try:
            callback = urlsplit(config['PAYSTACK_CALLBACK_URL'])
            callback_port = callback.port
        except ValueError:
            raise ImproperlyConfigured('Live callback must be an HTTPS URL.') from None
        require(callback.scheme == 'https' and bool(callback.hostname) and not callback.username
                and not callback.password and not callback.fragment and callback_port in (None, 443),
                'Live callback must be an HTTPS URL.')
    db=config.get('DATABASES',{}).get('default',{})
    require(db.get('ENGINE')=='django.db.backends.postgresql','Production requires PostgreSQL.')
    from .deployment_security import validate_database_tls
    validate_database_tls(config.get('DJANGO_DEPLOYMENT_TARGET', 'self-managed'),
                          db.get('HOST'), db.get('OPTIONS', {}).get('sslmode'))
    require(not any('MD5' in hasher for hasher in config.get('PASSWORD_HASHERS',[])),'Fast password hashers are test-only.')
    require(config.get('CACHES',{}).get('default',{}).get('BACKEND') not in
        (None,'django.core.cache.backends.locmem.LocMemCache','django.core.cache.backends.dummy.DummyCache'),
        'Production rate limiting requires a shared cache.')
