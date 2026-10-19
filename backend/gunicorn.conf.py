"""One bounded WSGI process; shared database cache supports future scaling."""
import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 60
graceful_timeout = 30
accesslog = None  # Do not log request paths, query strings or participant identifiers.
errorlog = '-'
loglevel = 'warning'
capture_output = False
