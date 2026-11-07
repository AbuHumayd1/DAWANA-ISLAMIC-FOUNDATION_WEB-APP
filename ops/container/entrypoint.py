"""Validate, render and supervise. Never migrate, seed or send messages."""
import os
from pathlib import Path
import signal
import subprocess
import sys
from gateway import configuration


def main():
    try:
        rendered = configuration(os.environ)
        required = {
            'DJANGO_SETTINGS_MODULE': 'config.settings.production',
            'DJANGO_DEPLOYMENT_TARGET': 'self-managed',
            'DJANGO_BIND_ADDRESS': '127.0.0.1', 'DJANGO_BIND_PORT': '10000',
            'DAWANA_TRUSTED_GATEWAYS': '127.0.0.1/32', 'DJANGO_TRUST_PROXY_HTTPS': 'true',
        }
        if any(os.environ.get(name) != value for name, value in required.items()):
            raise ValueError('Container Django/gateway security contract is incomplete.')
        if os.environ.get('DJANGO_ALLOWED_HOSTS') != os.environ['PUBLIC_HOST']:
            raise ValueError('Django must allow exactly the approved public hostname.')
        # Validate production settings without opening a DB connection.
        import django
        django.setup()
        from django.conf import settings
        origin = 'https://' + os.environ['PUBLIC_HOST']
        if settings.CSRF_TRUSTED_ORIGINS != [origin] or settings.CORS_ALLOWED_ORIGINS not in ([], [origin]):
            raise ValueError('Container requires exact same-origin CSRF/CORS configuration.')
        from config.runtime_requirements import verify_runtime
        verify_runtime()
        Path('/run/dawana/nginx.conf').write_text(rendered, encoding='utf-8')
        subprocess.run(['nginx', '-t', '-c', '/run/dawana/nginx.conf'], check=True)
    except Exception:
        # Settings/provider exceptions can contain supplied values; never echo.
        print('Container startup validation failed; review the documented configuration contract.', file=sys.stderr)
        return 1
    child = subprocess.Popen(['/usr/bin/supervisord', '-c', '/app/container/supervisord.conf'])
    def stop(signum, frame):
        child.send_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    status = child.wait()
    return 1 if Path('/run/dawana/child-failed').exists() else status


if __name__ == '__main__':
    sys.exit(main())
