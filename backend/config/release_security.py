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
    for key in ('SECURE_SSL_REDIRECT','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE'):
        require(config.get(key) is True,'Production HTTPS and secure cookies are required.')
    require(config.get('PAYSTACK_MODE')=='test','Live Paystack activation has not been approved.')
    key=config.get('PAYSTACK_SECRET_KEY','')
    require(not key or key.startswith('sk_test_'),'Production preparation accepts only test Paystack credentials.')
    db=config.get('DATABASES',{}).get('default',{})
    require(db.get('ENGINE')=='django.db.backends.postgresql','Production requires PostgreSQL.')
    require(db.get('OPTIONS',{}).get('sslmode') in ('require','verify-ca','verify-full'),'Production PostgreSQL must require TLS.')
    require(not any('MD5' in hasher for hasher in config.get('PASSWORD_HASHERS',[])),'Fast password hashers are test-only.')
    require(config.get('CACHES',{}).get('default',{}).get('BACKEND') not in
        (None,'django.core.cache.backends.locmem.LocMemCache','django.core.cache.backends.dummy.DummyCache'),
        'Production rate limiting requires a shared cache.')
