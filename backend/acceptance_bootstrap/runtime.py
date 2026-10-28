"""Database-free, process-local containment. No subprocess or socket bypass mode."""
from contextlib import ExitStack, contextmanager
import http.client
import os
import smtplib
import socket
import subprocess
import urllib.request
from unittest.mock import patch
from .config import IsolationError, require
from .payments import MockPaystack

_active = None


def deny(*args, **kwargs):
    raise IsolationError('Acceptance bootstrap blocks database/network/process side effects.')


def assert_active(config):
    require(_active is not None and _active[0] == config, 'Acceptance settings require the isolated bootstrap runtime.')


@contextmanager
def contained(config):
    global _active
    require(_active is None, 'Nested acceptance runtimes are prohibited.')
    gateway = MockPaystack()
    with ExitStack() as stack:
        for obj, name in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                (socket.socket, 'sendto'), (socket.socket, 'sendmsg'), (socket.socket, 'send'),
                (socket.socket, 'sendall'), (socket.socket, 'bind'), (socket, 'getaddrinfo'),
                (http.client.HTTPConnection, 'connect'), (http.client.HTTPSConnection, 'connect'),
                (urllib.request, 'urlopen'), (smtplib.SMTP, 'connect'),
                (subprocess, 'Popen'), (os, 'system'), (os, 'popen'),
                (os, 'posix_spawn'), (os, 'posix_spawnp'), (os, 'startfile')):
            if hasattr(obj, name):
                stack.enter_context(patch.object(obj, name, deny))
        _active = (config, gateway)
        try:
            yield gateway
        finally:
            _active = None


def attach_django(stack):
    """Call before django.setup inside contained(); never import application base settings."""
    require(_active is not None, 'Isolated runtime is not active.')
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.core.mail.backends.smtp import EmailBackend
    import dic.payments
    stack.enter_context(patch.object(BaseDatabaseWrapper, 'ensure_connection', deny))
    stack.enter_context(patch.object(EmailBackend, 'send_messages', deny))
    gateway = _active[1]
    def mock_request(client, method, path, payload=None):
        return gateway.request(method, path, payload)
    stack.enter_context(patch.object(dic.payments.PaystackClient, '_request', mock_request))
    stack.enter_context(patch.object(dic.payments, 'urlopen', deny))
