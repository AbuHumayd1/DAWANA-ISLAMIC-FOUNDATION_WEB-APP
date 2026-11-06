"""One bounded WSGI process; shared database cache supports future scaling."""
import os

# Render's port is exposed through its managed ingress, not a same-host Nginx.
if os.environ.get('DJANGO_DEPLOYMENT_TARGET') == 'render':
    port = int(os.environ.get('PORT', '10000'))
    if not 1 <= port <= 65535:
        raise ValueError('Invalid HTTP port.')
    bind = f'0.0.0.0:{port}'
else:
    bind = '127.0.0.1:10000'
forwarded_allow_ips = '127.0.0.1'
secure_scheme_headers = {'X-FORWARDED-PROTO': 'https'}
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 60
graceful_timeout = 30
accesslog = None  # Do not log request paths, query strings or participant identifiers.
errorlog = '-'
loglevel = 'warning'
capture_output = False
