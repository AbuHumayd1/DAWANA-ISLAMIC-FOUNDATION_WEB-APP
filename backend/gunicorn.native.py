"""Native managed service: Gunicorn serves the API, Admin and Django static files."""
import os

port = os.environ.get('PORT', '8080')
if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
    raise ValueError('PORT must be a valid service port.')
bind = '0.0.0.0:' + port
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 60
graceful_timeout = 30
# Django handles only the verified standard scheme header. Gunicorn must not
# independently interpret forwarded scheme headers from arbitrary peers.
forwarded_allow_ips = ''
secure_scheme_headers = {}
accesslog = None
errorlog = '-'
loglevel = 'warning'
capture_output = False
