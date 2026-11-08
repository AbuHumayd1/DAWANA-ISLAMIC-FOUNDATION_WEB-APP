"""Validate, render and supervise. Never migrate, seed or send messages."""
import os
from pathlib import Path
import signal
import subprocess
import sys
from gateway import configuration
from runtime_config import configure, validate_inputs
from startup_errors import StartupError


def stage(code, remedy, action):
    try:
        return action()
    except StartupError:
        raise
    except Exception:
        raise StartupError(code, remedy) from None


def django_contract(settings, host):
    origin = 'https://' + host
    if settings.ALLOWED_HOSTS != [host]:
        raise StartupError('DJ_HOSTS', 'Django must allow only PUBLIC_HOST; remove stale DJANGO_ALLOWED_HOSTS overrides.')
    if settings.CSRF_TRUSTED_ORIGINS != [origin] or settings.CORS_ALLOWED_ORIGINS not in ([], [origin]):
        raise StartupError('DJ_ORIGINS', 'Use the single PUBLIC_HOST HTTPS origin for CSRF and optional same-origin CORS.')
    if settings.DIC_BACKGROUND_WORKER_ENABLED:
        from dic.recovery import channel_available
        from dic.registration_accounts import verification_url
        if settings.DIC_AUTOMATION_ACTOR_ID <= 0 or not settings.DIC_PORTAL_ACCOUNTS_ENABLED or not channel_available('email'):
            raise StartupError('DJ_WORKERS', 'Full mode requires an automation actor, accounts and email recovery; use DAWANA_WEBSITE_ONLY=true for this release.')
        stage('DJ_EMAIL_URL', 'Configure the approved portal verification URL before full mode.', verification_url)


def main():
    try:
        stage('CFG_NORMALIZE', 'Review container-owned DJANGO_* overrides and website-only feature flags.', lambda: configure(os.environ))
        rendered = stage('GW_CONFIG', 'Review PUBLIC_HOST, PORT and the verified gateway TLS contract.', lambda: configuration(os.environ))
        stage('CFG_INPUTS', 'Review Django secret and PostgreSQL configuration without printing their values.', lambda: validate_inputs(os.environ))
        if os.environ.get('DATABASE_URL') and any(name in os.environ for name in ('DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_PORT')):
            print('Startup configuration [CFG_DB_PRECEDENCE]: DATABASE_URL takes precedence; legacy DB_* connection fields are ignored.', file=sys.stderr)
        # Validate production settings without opening a DB connection.
        import django
        stage('DJ_SETUP', 'Django settings/application loading failed; check remaining environment formats and the production settings contract.', django.setup)
        from django.conf import settings
        stage('DJ_CONTRACT', 'Review production host/origin and worker configuration.', lambda: django_contract(settings, os.environ['PUBLIC_HOST']))
        from config.runtime_requirements import verify_runtime
        stage('RUNTIME_REQUIREMENTS', 'Use the built production image with Python 3.13, pinned dependencies, fonts and executable ffprobe.', verify_runtime)
        stage('NGINX_WRITE', 'Provide writable /run/dawana owned by UID 10001.',
            lambda: Path('/run/dawana/nginx.conf').write_text(rendered, encoding='utf-8'))
        # Nginx error output may include configured paths/networks. Keep it private.
        stage('NGINX_VALIDATE', 'Nginx configuration/TLS files failed validation; verify direct-mode file mounts and permissions if used.',
            lambda: subprocess.run(['nginx', '-t', '-c', '/run/dawana/nginx.conf'], check=True, capture_output=True))
    except StartupError as error:
        print('Container startup validation failed [' + error.code + ']: ' + error.remedy, file=sys.stderr)
        return 1
    except Exception:
        print('Container startup validation failed [STARTUP_INTERNAL]: required runtime import failed; use the reviewed image.', file=sys.stderr)
        return 1
    try:
        child = stage('SUPERVISOR_START', 'Supervisor could not start; verify the image and writable runtime directory.',
            lambda: subprocess.Popen(['/usr/bin/supervisord', '-c', '/app/container/supervisord.conf']))
    except StartupError as error:
        print('Container startup failed [' + error.code + ']: ' + error.remedy, file=sys.stderr)
        return 1
    def stop(signum, frame):
        child.send_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    status = child.wait()
    return 1 if Path('/run/dawana/child-failed').exists() else status


if __name__ == '__main__':
    sys.exit(main())
