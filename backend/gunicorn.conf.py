"""One bounded WSGI process; shared database cache supports future scaling."""
import os

from config.deployment_security import application_bind

bind = application_bind(os.environ)
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
