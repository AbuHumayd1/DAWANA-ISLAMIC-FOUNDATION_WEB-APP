"""Test-only DIC Phase 3 acceptance. No migration, reset, delete or commit mode.

Writing commands need --confirm-demo-writes. All synthetic rows, including
browser fixtures, live in one rollback-only transaction. Never use manage.py test.
"""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import timedelta
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import sys
import threading
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
DATABASE = 'dic_2026_demo'
TARGET = ('dic', '0030_portal_account_authentication')
FORBIDDEN = ('dic', '0027_feedback_welfare')
RECEIPTS = ROOT / 'output' / 'acceptance'
IDENTIFIER = re.compile(r'^[a-z_][a-z0-9_]*$')
BROWSER_STAGES = frozenset(('browser_setup', 'backend_start', 'playwright_start', 'chromium_launch',
    'browser_context', 'registration_navigation', 'participant_form', 'checkout', 'payment_verification',
    'portal_navigation', 'setup_button', 'booking_reference', 'booking_contact', 'otp_request', 'otp_wait',
    'otp_entry', 'otp_verify', 'account_setup', 'account_activation', 'logout', 'password_login',
    'camper_switch', 'browser_cleanup', 'backend_task', 'backend_request', 'backend_failure',
    'options_django', 'options_wsgi_response', 'options_postprocessing'))


def safe_browser_failure(stage, error):
    """No free-form exception text, locators, URLs or page content in diagnostics."""
    stage = stage if stage in BROWSER_STAGES else 'unknown'
    category, hint = 'other_exception', 'inspect_failed_stage'
    cls = type(error)
    if cls.__module__.startswith('playwright.'):
        category = 'playwright_timeout' if cls.__name__ == 'TimeoutError' else 'playwright_error'
        # Match fixed signatures only; never retain the provider/locator text.
        message = str(error)
        for fragment, label in (('strict mode violation', 'locator_ambiguous'),
                ('Executable doesn', 'browser_executable_missing'), ('Target page, context or browser has been closed', 'browser_closed'),
                ('ERR_CONNECTION_REFUSED', 'local_connection_refused'), ('ERR_NAME_NOT_RESOLVED', 'name_resolution_failed'),
                ('not visible', 'element_not_visible'), ('not enabled', 'element_not_enabled')):
            if fragment in message:
                hint = label
                break
        else:
            if category == 'playwright_timeout': hint = 'operation_timed_out'
    else:
        for kind, label in ((StopAcceptance, 'guard_rejection'), (queue.Empty, 'backend_wait_timeout'),
                (TypeError, 'type_error'), (AttributeError, 'attribute_error'),
                (KeyError, 'key_error'), (ImportError, 'import_error'), (OSError, 'os_error')):
            if isinstance(error, kind):
                category = label
                break
    return {'stage': stage, 'category': category, 'hint': hint}


def record_browser_failure(receipt, stage, error):
    diagnostic = safe_browser_failure(stage, error)
    receipt.setdefault('browser_failures', []).append(diagnostic)
    return diagnostic


def safe_otp_probe(values):
    # Strict shape: never retain field values, DOM text, response bodies or URLs.
    keys = ('email_option_present', 'email_option_enabled', 'email_channel_selected',
        'reference_valid', 'contact_valid', 'button_disabled')
    return {key: values[key] for key in keys if type(values.get(key)) is bool}


def diagnose_otp_options():
    """Focused endpoint probes: no DB connections, mail or provider requests."""
    from django.test import Client, override_settings
    from django.db.backends.base.base import BaseDatabaseWrapper
    from rest_framework.test import APIRequestFactory
    from dic.participant_api import PortalOptionsView
    from dic.recovery import available_channels
    results = {}
    with override_settings(DIC_EMAIL_RECOVERY_ENABLED=True, DIC_RECOVERY_DELIVERY_WORKER_ENABLED=True,
            DEBUG=False), patch.object(BaseDatabaseWrapper, 'ensure_connection', denied):
        operations = (
            ('available_channels', lambda: available_channels()),
            ('view_and_render', lambda: PortalOptionsView.as_view()(APIRequestFactory().get('/api/v1/dic/participant/auth/options/')).render()),
            ('middleware_request', lambda: Client().get('/api/v1/dic/participant/auth/options/')),
        )
        for operation, function in operations:
            try:
                result = function()
                results[operation] = {'passed': True}
                if hasattr(result, 'status_code'):
                    results[operation]['http_status'] = result.status_code
                    results[operation]['passed'] = result.status_code == 200
                else:
                    results[operation]['email_available'] = any(item.key == 'email' and item.available for item in result)
            except Exception as error:
                diagnostic = safe_browser_failure('options_django', error)
                results[operation] = {'passed': False, 'category': diagnostic['category'], 'hint': diagnostic['hint']}
    return results


class StopAcceptance(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise StopAcceptance(message)


def denied(*args, **kwargs):
    raise StopAcceptance('Forbidden external, destructive or unguarded operation.')


def require_browser_prerequisites(prerequisites):
    missing = []
    if not prerequisites.get('frontend_build'):
        missing.append('frontend build: run npm.cmd run build in dawana-platform')
    if not prerequisites.get('playwright_package'):
        missing.append('Python Playwright: install playwright in backend/.venv, then install its Chromium binaries')
    require(not missing, 'Browser prerequisites missing: '+ '; '.join(missing))


def make_loopback_socketpair(real_connect):
    """Private Windows event-loop wakeup pair; never opens a general port rule."""
    def socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        require(family in (socket.AF_INET, socket.AF_INET6) and type == socket.SOCK_STREAM
            and proto == 0, 'Unsupported internal socketpair.')
        host = '127.0.0.1' if family == socket.AF_INET else '::1'
        listener = socket.socket(family, type, proto)
        client = server = None
        try:
            listener.bind((host, 0))
            listener.listen(1)
            listener.settimeout(5)
            destination = listener.getsockname()
            client = socket.socket(family, type, proto)
            client.settimeout(5)
            # Only this freshly created socket may reach this owned listener.
            real_connect(client, destination)
            server, _ = listener.accept()
            require(server.getpeername() == client.getsockname()
                and client.getpeername() == server.getsockname(), 'Internal socketpair peer mismatch.')
            client.settimeout(None); server.settimeout(None)
            return server, client
        except BaseException:
            if client is not None: client.close()
            if server is not None: server.close()
            raise
        finally:
            listener.close()
    return socketpair


def configure(requested, writing):
    """Read only connection credentials; pin target BEFORE any Django import."""
    require(requested == DATABASE, 'Only dic_2026_demo is authorized.')
    require('django.conf' not in sys.modules, 'Run in a fresh Python process.')
    import environ
    environ.Env.read_env(ROOT / 'backend' / '.env')
    env = environ.Env()
    # DATABASE_URL may supply credentials, NEVER the selected database name.
    if env('DATABASE_URL', default=''):
        source = env.db_url('DATABASE_URL')
        require(source['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL required.')
    else:
        source = dict(HOST=env('DB_HOST', default='127.0.0.1'), PORT=env('DB_PORT', default='5432'),
            USER=env('DB_USER'), PASSWORD=env('DB_PASSWORD', default=''))
    require(source.get('HOST') in ('localhost', '127.0.0.1', '::1'), 'Loopback PostgreSQL required.')
    port = int(source.get('PORT') or 5432)
    require(1 <= port <= 65535, 'Invalid PostgreSQL port.')
    from cryptography.fernet import Fernet
    marker = uuid.uuid4().hex
    # Prevent Playwright debug traces from recording synthetic passwords/codes.
    os.environ.pop('DEBUG', None)
    os.environ.pop('PWDEBUG', None)
    os.environ.pop('PLAYWRIGHT_NODEJS_PATH', None)
    os.environ.pop('PGSERVICE', None)
    os.environ.pop('PGSERVICEFILE', None)
    os.environ.update(DATABASE_URL='', DB_NAME=DATABASE, DB_HOST='127.0.0.1', DB_PORT=str(port),
        DB_USER=source['USER'], DB_PASSWORD=source.get('PASSWORD') or '', DB_TEST_NAME='test_dic_phase3_never_create',
        DJANGO_SETTINGS_MODULE='config.settings.development', DJANGO_DEBUG='True',
        DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_ALLOWED_HOSTS='127.0.0.1,localhost,testserver',
        DIC_PORTAL_ACCOUNTS_ENABLED='True', DIC_ASSISTED_BOOKING_ENABLED='False',
        DIC_GOOGLE_CLIENT_ID='', DIC_GOOGLE_CLIENT_SECRET='', DIC_GOOGLE_REDIRECT_URI='', DIC_PORTAL_FRONTEND_URL='',
        DIC_PORTAL_EMAIL_VERIFY_URL='https://acceptance.example.test/dic/participant',
        PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_acceptance_no_network', PAYSTACK_CALLBACK_URL='',
        DIC_EMAIL_RECOVERY_ENABLED='True' if writing else 'False',
        DIC_RECOVERY_DELIVERY_WORKER_ENABLED='True' if writing else 'False',
        DIC_RECOVERY_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='acceptance.invalid',
        EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='', DEFAULT_FROM_EMAIL='acceptance@example.test',
        DIC_SMS_RECOVERY_ADAPTER='', DIC_WHATSAPP_ACCESS_TOKEN='', DIC_WHATSAPP_PHONE_NUMBER_ID='',
        DIC_MEMORY_STORAGE='disabled', DIC_MEMORY_S3_BUCKET='', DIC_MEMORY_S3_ENDPOINT='',
        AWS_EC2_METADATA_DISABLED='true', AWS_ACCESS_KEY_ID='synthetic', AWS_SECRET_ACCESS_KEY='synthetic',
        AWS_SESSION_TOKEN='', SESSION_COOKIE_SECURE='False')
    os.environ['PGOPTIONS'] = '-c default_transaction_read_only=on -c statement_timeout=10000'
    sys.path.insert(0, str(ROOT / 'backend'))
    return port, marker


@contextmanager
def guards(port, allowed_http, allow_browser=False):
    """Install before django.setup(), then keep installed through teardown."""
    import http.client
    import smtplib
    import urllib.request
    import psycopg
    import subprocess
    from psycopg.conninfo import conninfo_to_dict
    real_connect = psycopg.connect
    real_socket_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo
    real_popen_init = subprocess.Popen.__init__

    def popen_init(process, args, *extra, **kwargs):
        require(allow_browser and isinstance(args, (list, tuple)) and len(args) == 3
            and args[2] == 'run-driver' and not kwargs.get('shell'), 'Subprocess blocked.')
        import playwright
        driver = Path(playwright.__file__).resolve().parent / 'driver'
        require(Path(args[0]).resolve() in ((driver/'node.exe').resolve(), (driver/'node').resolve())
            and Path(args[1]).resolve() == (driver/'package/cli.js').resolve(), 'Only the packaged browser driver may start.')
        require(not kwargs.get('executable') or Path(kwargs['executable']).resolve() == Path(args[0]).resolve(), 'Executable override refused.')
        if kwargs.get('env'):
            kwargs['env'] = {key: value for key, value in kwargs['env'].items() if key not in
                ('DATABASE_URL', 'DB_PASSWORD', 'PGPASSWORD', 'DJANGO_SECRET_KEY', 'PAYSTACK_SECRET_KEY',
                 'DIC_RECOVERY_ENCRYPTION_KEY', 'DIC_GOOGLE_CLIENT_SECRET', 'EMAIL_HOST_PASSWORD')}
        return real_popen_init(process, args, *extra, **kwargs)

    def pg_connect(conninfo='', **kwargs):
        info = conninfo_to_dict(conninfo, **{k: v for k, v in kwargs.items()
            if k not in ('autocommit', 'row_factory', 'cursor_factory', 'context', 'prepare_threshold')})
        require(info.get('dbname') == DATABASE and info.get('host') in ('127.0.0.1', 'localhost', '::1')
            and int(info.get('port', 5432)) == port and not info.get('service'), 'Refusing another database connection.')
        return real_connect(conninfo, **kwargs)

    def connect(sock, address):
        require(isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')
            and address[1] in {port, *allowed_http}, 'Network destination blocked.')
        return real_socket_connect(sock, address)

    def resolve(host, target_port, *args, **kwargs):
        require(host in ('127.0.0.1', 'localhost', '::1') and int(target_port) in {port, *allowed_http}, 'External DNS blocked.')
        return real_getaddrinfo(host, target_port, *args, **kwargs)

    with ExitStack() as stack:
        previous_logging = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        stack.callback(logging.disable, previous_logging)
        stack.enter_context(patch.object(psycopg, 'connect', pg_connect))
        stack.enter_context(patch.object(socket.socket, 'connect', connect))
        stack.enter_context(patch.object(socket.socket, 'connect_ex', denied))
        if allow_browser and sys.platform == 'win32':
            stack.enter_context(patch.object(socket, 'socketpair', make_loopback_socketpair(real_socket_connect)))
        stack.enter_context(patch.object(socket, 'getaddrinfo', resolve))
        stack.enter_context(patch.object(urllib.request, 'urlopen', denied))
        stack.enter_context(patch.object(http.client.HTTPConnection, 'connect', denied))
        stack.enter_context(patch.object(http.client.HTTPSConnection, 'connect', denied))
        stack.enter_context(patch.object(smtplib, 'SMTP', denied))
        stack.enter_context(patch.object(smtplib, 'SMTP_SSL', denied))
        stack.enter_context(patch.object(subprocess.Popen, '__init__', popen_init))
        from django.db.backends.base.base import BaseDatabaseWrapper
        original_ensure = BaseDatabaseWrapper.ensure_connection

        def ensure(connection):
            config = connection.settings_dict
            require(connection.alias == 'default' and config['NAME'] == DATABASE
                and config['HOST'] == '127.0.0.1' and int(config['PORT']) == port, 'Unexpected Django database.')
            return original_ensure(connection)

        stack.enter_context(patch.object(BaseDatabaseWrapper, 'ensure_connection', ensure))
        from django.core import management
        stack.enter_context(patch.object(management, 'call_command', denied))
        stack.enter_context(patch.object(management, 'execute_from_command_line', denied))
        from django.db.backends.base.creation import BaseDatabaseCreation
        stack.enter_context(patch.object(BaseDatabaseCreation, 'create_test_db', denied))
        stack.enter_context(patch.object(BaseDatabaseCreation, 'destroy_test_db', denied))
        from django.db.migrations.executor import MigrationExecutor
        stack.enter_context(patch.object(MigrationExecutor, 'migrate', denied))
        from django.db.backends.utils import CursorWrapper
        original_execute = CursorWrapper.execute

        def execute(cursor, sql, params=None):
            require(isinstance(sql, str), 'Unrecognized SQL representation.')
            verb = sql.strip().split(None, 1)[0].upper() if sql.strip() else ''
            require(verb in ('SELECT', 'INSERT', 'UPDATE', 'BEGIN', 'SAVEPOINT', 'RELEASE', 'ROLLBACK', 'SET'), 'SQL operation blocked.')
            if verb in ('INSERT', 'UPDATE'):
                require(any(isinstance(wrapper, Inventory) for wrapper in cursor.db.execute_wrappers), 'Write outside rollback/ownership guard refused.')
            return original_execute(cursor, sql, params)

        stack.enter_context(patch.object(CursorWrapper, 'execute', execute))
        stack.enter_context(patch.object(CursorWrapper, 'executemany', denied))
        stack.enter_context(patch.object(CursorWrapper, 'callproc', denied))
        yield stack


def identity(connection, port, readonly=False):
    require(connection.settings_dict['NAME'] == DATABASE, 'Resolved database mismatch.')
    with connection.cursor() as cursor:
        # inet::text includes /32 or /128; host(inet) returns the exact address.
        cursor.execute('SELECT current_database(), host(inet_server_addr()), inet_server_port(), current_setting(\'transaction_read_only\')')
        name, host, actual_port, read_only = cursor.fetchone()
    require(name == DATABASE and host in ('127.0.0.1', '::1') and actual_port == port, 'PostgreSQL identity mismatch.')
    if readonly:
        require(read_only == 'on', 'Preflight must be read-only.')
    return {'database': name, 'host': host, 'port': actual_port}


def schema(connection):
    from django.apps import apps
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.state import ProjectState
    loader = MigrationLoader(connection)
    require(not loader.detect_conflicts() and FORBIDDEN not in loader.applied_migrations, 'Unsafe migration history.')
    plan = loader.graph.forwards_plan(TARGET)
    require(FORBIDDEN not in plan and all(node in loader.applied_migrations for node in plan), 'Required schema is incomplete.')
    names = ('PortalAccount', 'PortalAccountBooking', 'PortalAccountSession', 'PortalGoogleLink', 'PortalOAuthAttempt',
        'ParticipantPortalGrant', 'ParticipantPortalScope', 'ParticipantPortalChallenge', 'RegistrationOrder',
        'RegistrationOrderItem', 'PaymentAttempt', 'RegistrationOrderPriceRevision', 'CampEnrollment',
        'TutorRegistrationAuthorization', 'TutorVerification')
    tables = set(connection.introspection.table_names())
    for name in names:
        model = apps.get_model('dic', name)
        require(model._meta.db_table in tables, 'Required table missing: ' + model._meta.db_table)
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, model._meta.db_table)}
        require({field.column for field in model._meta.local_fields} <= columns, 'Required columns missing: ' + name)
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
        for field in model._meta.local_fields:
            if field.is_relation:
                target = (field.remote_field.model._meta.db_table, field.target_field.column)
                require(any(item.get('foreign_key') == target and item['columns'] == [field.column]
                    for item in constraints.values()), 'Required foreign key missing: ' + name)
            if field.unique:
                require(any((item.get('unique') or item.get('primary_key')) and item['columns'] == [field.column]
                    for item in constraints.values()), 'Required uniqueness missing: ' + name)
    actual, prepared = ProjectState.from_apps(apps), loader.project_state(TARGET)
    for name in ('portalaccount', 'portalaccountbooking', 'portalaccountsession', 'portalgooglelink', 'portaloauthattempt'):
        require(actual.models['dic', name] == prepared.models['dic', name], 'Prepared account model state mismatch.')
    return {'target': '.'.join(TARGET), 'deferred_0027_applied': False, 'core_tables_checked': len(names)}


def fixture_requirements():
    from dic.models import CampEdition
    from django.utils import timezone
    rows = list(CampEdition.objects.filter(is_active=True))
    require(len(rows) <= 1, 'Multiple active editions: fixture selection is ambiguous.')
    if not rows:
        require(not CampEdition.objects.filter(year=2026).exists(),
            'An inactive pre-existing 2026 edition occupies the unique year; it will not be modified.')
        return {'edition': 'create_owned_synthetic_edition_inside_rollback'}
    edition = rows[0]
    today = timezone.localdate()
    require(edition.year == 2026 and edition.registration_status == 'open'
        and edition.registration_open_date and edition.registration_close_date
        and edition.registration_open_date <= today <= edition.registration_close_date
        and edition.camp_end_date >= today and edition.tutor_registration_enabled,
        'Existing active edition is not ready for all scenarios; it will not be modified.')
    require(not edition.pricing_configuration_errors(), 'Existing edition pricing is incomplete; no changes made.')
    return {'edition': 'reuse_existing_approved_configuration', 'edition_id': edition.pk}


class Inventory:
    """Rollback ledger plus SQL guard: UPDATE can touch only new transaction rows."""
    def __init__(self, connection):
        from django.apps import apps
        self.connection = connection
        tables = set(connection.introspection.table_names())
        self.keys = {model._meta.db_table: model._meta.pk.column
            for model in apps.get_models(include_auto_created=True) if model._meta.db_table in tables}
        self.baseline = {table: self.ids(table) for table in self.keys}
        self.owned = {table: set() for table in self.keys}

    def ids(self, table, where='', params=()):
        column = self.keys[table]
        require(IDENTIFIER.fullmatch(table) and IDENTIFIER.fullmatch(column), 'Unexpected SQL identifier.')
        with self.connection.cursor() as cursor:
            cursor.execute(f'SELECT "{column}" FROM "{table}"' + (' WHERE '+where if where else ''), params)
            return {str(row[0]) for row in cursor.fetchall()}

    def __call__(self, execute, sql, params, many, context):
        text = sql.strip()
        require(';' not in text and '--' not in text and '/*' not in text, 'Multi-statement or commented SQL refused.')
        verb = text.split(None, 1)[0].upper() if text else ''
        require(verb in ('SELECT', 'INSERT', 'UPDATE', 'SAVEPOINT', 'RELEASE', 'ROLLBACK', 'SET'),
            'SQL operation refused; no DDL, DELETE, flush, reset or commit is allowed.')
        if verb == 'INSERT':
            match = re.match(r'INSERT INTO "([a-z_][a-z0-9_]*)"', text, re.I)
            require(match and match[1] in self.keys and not many, 'Unrecognized INSERT.')
            table = match[1]
            result = execute(sql, params, many, context)
            self.owned[table] = self.ids(table) - self.baseline[table]
            return result
        if verb == 'UPDATE':
            match = re.match(r'UPDATE "([a-z_][a-z0-9_]*)" SET (.*?) WHERE (.*)', text, re.I | re.S)
            require(match and match[1] in self.keys and not many, 'Unbounded UPDATE refused.')
            table, assignments, where = match.groups()
            affected = self.ids(table, where, tuple(params or ())[assignments.count('%s'):])
            require(affected <= self.owned[table], 'UPDATE of pre-existing records refused.')
        return execute(sql, params, many, context)

    def fixtures(self):
        return {table: sorted(values) for table, values in self.owned.items() if values}

    def verify_rollback(self):
        require(all(self.ids(table) == values for table, values in self.baseline.items()), 'Rollback inventory mismatch.')


class Scenario:
    def __init__(self, marker):
        self.marker = marker
        self.mailbox = {}
        self.email_links = {}
        self.references = {}
        self.checks = []
        self.password = secrets.token_urlsafe(24)+'!9a'
        self.category = None
        self.owner = marker+'.owner@example.test'
        self.counter = 0
        self.last_booking = None
        self.clock_start = None
        self.clock_seconds = 0

    def capture_mail(self, channel, destination, code):
        require(channel == 'email' and destination.startswith(self.marker+'.')
            and destination.endswith('@example.test'), 'Non-synthetic delivery refused.')
        self.mailbox[destination] = code

    def capture_email_link(self, subject, message, sender, recipients, **kwargs):
        require(len(recipients) == 1 and recipients[0].startswith(self.marker+'.')
            and recipients[0].endswith('@example.test'), 'Non-synthetic verification email refused.')
        token = message.split('#verify-email=', 1)[1].splitlines()[0]
        self.email_links[recipients[0]] = token
        return 1

    def initialize(self, client, **kwargs):
        require(kwargs['email'].startswith(self.marker+'.'), 'Non-synthetic provider request refused.')
        reference = kwargs['reference']
        self.references[reference] = {'amount': kwargs['amount_kobo'], 'status': 'success', 'id': uuid.uuid4().int}
        return {'authorization_url': 'https://checkout.paystack.com/acceptance-blocked', 'reference': reference}

    def verify(self, client, reference):
        from django.utils import timezone
        require(reference in self.references, 'Unknown provider reference refused.')
        data = self.references[reference]
        return {'id': data['id'], 'domain': 'test', 'reference': reference,
            'amount': data['amount'], 'currency': 'NGN', 'status': data['status'], 'paid_at': timezone.now().isoformat()}

    def install(self, stack):
        from dic.payments import PaystackClient
        stack.enter_context(patch('dic.registration_accounts.send_mail', self.capture_email_link))
        stack.enter_context(patch.object(PaystackClient, 'initialize_transaction', autospec=True, side_effect=self.initialize))
        stack.enter_context(patch.object(PaystackClient, 'verify_transaction', autospec=True, side_effect=self.verify))
        for target in ('dic.recovery.send_recovery_code', 'dic.tutor_registration_api.send_recovery_code',
            'dic.management.commands.send_dic_portal_messages.send_recovery_code',
            'dic.management.commands.send_dic_recovery_messages.send_recovery_code'):
            stack.enter_context(patch(target, self.capture_mail))
        from django.core.mail.backends.smtp import EmailBackend
        stack.enter_context(patch.object(EmailBackend, 'send_messages', denied))
        from django.utils import timezone
        self.clock_start = timezone.now()
        stack.enter_context(patch.object(timezone, 'now', lambda: self.clock_start+timedelta(seconds=self.clock_seconds)))
        from django.conf import settings
        settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': self.marker}}
        settings.SESSION_COOKIE_SECURE = False
        settings.CSRF_COOKIE_SECURE = False
        settings.DEBUG = False

    def client(self):
        from django.test import Client
        self.counter += 1
        return Client(enforce_csrf_checks=True, REMOTE_ADDR=f'127.9.{int(self.marker[:2],16)}.{self.counter}')

    def request(self, client, path, data=None, expected=200, bearer=None, key=None):
        headers = {}
        if bearer: headers['HTTP_AUTHORIZATION'] = 'Bearer '+bearer
        if key: headers['HTTP_IDEMPOTENCY_KEY'] = key
        if data is None:
            response = client.get('/api/v1/dic/'+path, **headers)
        else:
            token = client.get('/api/v1/dic/participant/auth/csrf/').json()['csrfToken']
            response = client.post('/api/v1/dic/'+path, data, content_type='application/json', HTTP_X_CSRFTOKEN=token, **headers)
        allowed = (expected,) if isinstance(expected, int) else expected
        safe_path = path if path in ('participant/auth/challenges/', 'participant/auth/verify/',
            'participant/auth/account/activate/', 'participant/auth/password/login/',
            'participant/auth/password/reset/', 'participant/auth/account/link-booking/',
            'participant/auth/me/', 'participant/auth/logout/', 'participant/enrollments/', 'orders/') else path.split('/')[0]
        require(response.status_code in allowed, 'Unexpected HTTP status at '+safe_path+': '+str(response.status_code))
        return response.json() if response.content else {}

    def seed(self):
        from dic.models import CampEdition, RegistrationCategory
        from django.utils import timezone
        fixture_requirements()
        today = timezone.localdate()
        edition = CampEdition.objects.filter(is_active=True).first()
        if edition is None:
            edition = CampEdition.objects.create(name='SYNTHETIC Phase3 '+self.marker, year=2026,
                is_active=True, registration_status='open', registration_open_date=today-timedelta(days=1),
                registration_close_date=today+timedelta(days=30), camp_start_date=today+timedelta(days=35),
                camp_end_date=today+timedelta(days=45), tutor_registration_enabled=True)
        self.edition = edition
        self.category = RegistrationCategory.objects.create(edition=edition, name='SYNTHETIC '+self.marker,
            fee_ngn='12500.00', early_bird_fee_ngn='6250.00' if edition.early_bird_cutoff_at else None, is_active=True)

    def person(self, tag):
        return {'category_id': self.category.pk, 'full_name': 'SYNTHETIC '+self.marker+' '+tag,
            'address': 'Synthetic acceptance only', 'phone': '08012345678', 'email': self.marker+'.'+tag+'@example.test',
            'age_declaration': 'adult', 'date_of_birth': None, 'sex': 'Male', 'height_cm': None, 'weight_kg': None,
            'academic_status': 'Not Currently in School', 'occupation': 'None', 'marital_status': 'None'}

    def register(self, tag, count=1, email=None, legacy=False):
        client = self.client()
        people = [self.person(tag+str(i)) for i in range(count)]
        if count > 1:
            from django.utils import timezone
            for index, person in enumerate(people):
                person.update(age_declaration='minor', date_of_birth=f'{timezone.localdate().year-10-index*2}-01-01')
        payload = {'primary_registrant': {'full_name': 'SYNTHETIC booker', 'email': email or self.owner}, 'participants': people}
        if legacy:
            from dic.assisted_registration import AssistedOrderInput
            from dic.views import _create_order, _request_fingerprint, _order_summary
            from dic.security import digest_value
            serializer = AssistedOrderInput(data=payload); serializer.is_valid(raise_exception=True)
            order, token, _ = _create_order(key_digest=digest_value(str(uuid.uuid4())),
                fingerprint=_request_fingerprint(serializer.validated_data), payload=serializer.validated_data)
            result = _order_summary(order, token)
        else:
            payload['portal_account'] = {'password': self.password, 'password_confirmation': self.password}
            result = self.request(client, 'orders/', payload, expected=201, key=str(uuid.uuid4()))
        return {'client': client, 'order': result['order_id'], 'token': result['access_token'], 'email': email or self.owner}

    def verification_link(self, email):
        self.request(self.client(), 'participant/auth/email/resend/', {'identifier': email, 'password': self.password}, expected=202)
        require(email in self.email_links, 'Synthetic verification email not captured.')
        return self.email_links.pop(email)

    def settle(self, booking, status='success', mismatched=False):
        initialized = self.request(booking['client'], 'orders/'+booking['order']+'/payments/initialize/', {}, bearer=booking['token'])
        reference = initialized['payment_reference']
        self.references[reference]['status'] = status
        if mismatched: self.references[reference]['amount'] += 1
        self.request(booking['client'], 'orders/'+booking['order']+'/payments/'+reference+'/verify/', {},
            bearer=booking['token'], expected=(200, 400, 409))
        if status == 'success' and not mismatched:
            from dic.models import RegistrationOrder
            from dic.portal_accounts import booking_eligible
            require(booking_eligible(RegistrationOrder.objects.get(public_id=booking['order'])),
                'Mocked successful payment did not establish trusted booking eligibility.')

    def deliver_queued(self):
        from dic.models import ParticipantPortalChallenge
        from dic.management.commands.send_dic_portal_messages import process_portal_challenge
        for challenge in ParticipantPortalChallenge.objects.filter(delivery_status='queued', order__primary_registrant__email__startswith=self.marker+'.'):
            process_portal_challenge(challenge.pk)

    def otp(self, booking, client=None, accepted=True):
        # Honor the real 60-second resend cooldown using an isolated test clock.
        self.clock_seconds += 61
        client = client or self.client()
        start = self.request(client, 'participant/auth/challenges/', {'channel': 'email', 'contact': booking['email'], 'order_reference': booking['order']}, expected=202)
        self.deliver_queued()
        require(booking['email'] in self.mailbox, 'Synthetic OTP was not captured.')
        self.request(client, 'participant/auth/verify/', {'challenge_id': start['challenge_id'], 'code': self.mailbox.pop(booking['email'])}, expected=200 if accepted else 400)
        return client

    def activate(self, client, email, username):
        self.request(client, 'participant/auth/account/activate/', {'username': username, 'email': email,
            'password': self.password, 'password_confirmation': self.password})

    def login(self, email, password=None):
        client = self.client()
        self.request(client, 'participant/auth/password/login/', {'identifier': email, 'password': password or self.password})
        return client

    def orders(self, client):
        return self.request(client, 'participant/enrollments/')['orders']

    def integration(self):
        from dic.models import RegistrationOrder
        new_email = self.marker+'.new@example.test'
        new = self.register('new', email=new_email)
        self.request(self.client(), 'participant/auth/password/login/', {'identifier': new_email, 'password': self.password}, expected=403)
        token = self.verification_link(new_email)
        self.request(self.client(), 'participant/auth/email/verify/', {'token': token})
        self.request(self.client(), 'participant/auth/email/verify/', {'token': token}, expected=400)
        self.request(self.client(), 'participant/auth/password/login/', {'identifier': new_email, 'password': self.password}, expected=403)
        self.settle(new)
        require(len(self.orders(self.login(new_email))) == 1, 'Pre-payment credentials did not unlock after verified settlement.')
        self.checks.append('registration_password_email_link_pending_denial_verified_payment_login')
        paid = self.register('paid', 2, legacy=True); self.otp(paid, accepted=False)
        self.settle(paid)
        proof = self.otp(paid); username = 'accept_'+self.marker[:20]
        self.activate(proof, self.owner, username)
        client = self.login(self.owner)
        records = self.orders(client)
        require(len(records) == 1 and len(records[0]['participants']) == 2, 'Paid guardian scope mismatch.')
        self.checks.append('paid_multichild_otp_activation_password_login')
        second = self.register('second'); self.settle(second)
        other = self.register('foreign', email=self.marker+'.foreign@example.test'); self.settle(other)
        unpaid = self.register('unpaid')
        failed = self.register('failed'); self.settle(failed, status='failed')
        unverified = self.register('unverified'); self.settle(unverified, mismatched=True)
        for booking in (unpaid, failed, unverified): self.otp(booking, accepted=False)
        require({row['reference'] for row in self.orders(client)} == {paid['order']}, 'Unlinked bookings disclosed.')
        # The real contact limit is five requests/hour. Advance the isolated
        # clock rather than weakening/resetting application throttling rules.
        self.clock_seconds += 3601
        second_proof = self.otp(second)
        self.request(second_proof, 'participant/auth/account/link-booking/', {'identifier': self.owner, 'password': self.password})
        client = self.login(self.owner)
        expiry_client = self.login(self.owner)
        from dic.models import ParticipantPortalGrant
        from dic.participant_api import COOKIE
        from django.utils import timezone
        from dic.security import digest_value
        ParticipantPortalGrant.objects.filter(credential_digest=digest_value(expiry_client.cookies[COOKIE].value)).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.request(expiry_client, 'participant/auth/me/', expected=403)
        require({row['reference'] for row in self.orders(client)} == {paid['order'], second['order']}, 'Explicit guardian linking failed.')
        from dic.models import CampEnrollment
        foreign = CampEnrollment.objects.filter(source_item__order__public_id=other['order']).first()
        self.request(client, 'participant/enrollments/'+str(foreign.pk)+'/id/', expected=404)
        self.checks.append('separate_orders_foreign_child_unpaid_failed_unverified_denied')
        RegistrationOrder.objects.filter(public_id=paid['order']).update(payment_status='refunded')
        require({row['reference'] for row in self.orders(client)} == {second['order']}, 'Refunded scope retained.')
        recovery = self.otp(second)
        old_password = self.password; self.password = secrets.token_urlsafe(24)+'!9a'
        self.request(recovery, 'participant/auth/password/reset/', {'password': self.password})
        self.request(client, 'participant/auth/me/', expected=403)
        self.request(self.client(), 'participant/auth/password/login/', {'identifier': self.owner, 'password': old_password}, expected=403)
        client = self.login(self.owner)
        RegistrationOrder.objects.filter(public_id=second['order']).update(payment_status='refunded')
        self.request(client, 'participant/auth/me/', expected=403)
        self.request(client, 'participant/auth/logout/', {}, expected=204)
        self.checks.append('returning_setup_recovery_refund_expiry_session_invalidation_logout')
        self.tutor()

    def tutor(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from dic.tutor_registration import authorize, issue
        from dic.models import CampEnrollment, RegistrationOrder
        from dic.housing_policy import validate_occupant
        from dic.activity_scoring_api import camper_scores
        from django.core.exceptions import ValidationError
        actor = get_user_model().objects.create_user(username='staff_'+self.marker[:20], password=secrets.token_urlsafe(32), is_staff=True)
        permission = Permission.objects.get(content_type__app_label='dic', content_type__model='tutorregistrationauthorization', codename='can_authorize_dic_tutors')
        actor.user_permissions.add(permission)
        email = self.marker+'.tutor@example.test'; person = self.person('tutor'); person['email'] = email; person.pop('category_id')
        authorization = authorize(actor, self.edition, person['full_name'], email, 'Synthetic acceptance only')
        invitation = issue(actor, authorization.pk, 'Synthetic acceptance only')
        client = self.client()
        start = self.request(client, 'tutor-registration/challenges/', {'invitation': invitation}, expected=202)
        self.request(client, 'tutor-registration/verify/', {'verification_id': start['verification_id'], 'code': self.mailbox.pop(email)})
        redeemed = self.request(client, 'tutor-registration/redeem/', {'verification_id': start['verification_id'], 'participant': person})
        order = RegistrationOrder.objects.get(public_id=redeemed['order_id'])
        require(order.payment_status == 'not_required' and not order.payment_attempts.exists(), 'Tutor settlement invariant failed.')
        proof = self.otp({'order': str(order.public_id), 'email': email})
        self.activate(proof, email, 'tutor_'+self.marker[:20])
        require(self.orders(self.login(email))[0]['registration_basis'] == 'tutor', 'Tutor portal unavailable.')
        enrollment = CampEnrollment.objects.get(source_item__order=order)
        try:
            validate_occupant(enrollment.participant, self.edition, object())
        except ValidationError:
            pass
        else:
            raise StopAcceptance('Tutor housing exclusion failed.')
        require(not camper_scores(order.items.get(), 1)['competitive'], 'Tutor competition exclusion failed.')
        self.checks.append('complimentary_tutor_otp_portal_housing_competition_exclusions')


def write_receipt(path, receipt):
    require(path.parent.resolve() == RECEIPTS.resolve(), 'Receipt directory mismatch.')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


@contextmanager
def rollback_run(connection, receipt, path):
    from django.db import transaction
    from django.contrib.contenttypes.models import ContentType
    ContentType.objects.clear_cache()
    inventory = None
    receipt['cleanup'] = 'rollback_pending'
    write_receipt(path, receipt)
    try:
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                identity(connection, int(connection.settings_dict['PORT']))
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [2026102703])
                    require(cursor.fetchone()[0], 'Another acceptance transaction is active.')
                    cursor.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()')
                    require(cursor.fetchone()[0] == 0, 'Close other demo database sessions before writing acceptance.')
                inventory = Inventory(connection)
                receipt['baseline'] = {table: {'count': len(ids), 'ids_digest': hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()}
                    for table, ids in inventory.baseline.items()}
                with connection.execute_wrapper(inventory), patch.object(connection, 'commit', denied):
                    yield inventory
            finally:
                if inventory:
                    batch = {'fixtures': inventory.fixtures(), 'cleanup': 'rollback_pending'}
                    receipt.setdefault('batches', []).append(batch)
                    for table, ids in batch['fixtures'].items():
                        receipt['fixtures'].setdefault(table, []).extend(ids)
                transaction.set_rollback(True)
    finally:
        ContentType.objects.clear_cache()
        if inventory:
            inventory.verify_rollback()
            batch['cleanup'] = 'rollback_verified_no_retained_rows'
            receipt['cleanup'] = 'rollback_verified_no_retained_rows'
        write_receipt(path, receipt)


def browser_run(scenario, receipt, path, port, allowed_http):
    """Single-thread WSGI owns the rollback transaction; browser sees its rows."""
    stage = 'browser_setup'
    receipt['browser_stage'] = stage
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    from playwright.sync_api import sync_playwright
    from django.core.wsgi import get_wsgi_application
    from django.core import signals
    from django.db import connections, close_old_connections
    from django.conf import settings
    dist = ROOT / 'dawana-platform' / 'dist'
    require((dist / 'index.html').is_file(), 'Build frontend before browser acceptance.')
    jobs = queue.Queue(); ready = queue.Queue(); failures = queue.Queue()
    stopped = threading.Event()
    django_app = get_wsgi_application()
    signals.request_started.disconnect(close_old_connections)
    signals.request_finished.disconnect(close_old_connections)
    def options_exception(sender, request, **kwargs):
        if request.path == '/api/v1/dic/participant/auth/options/':
            record_browser_failure(receipt, 'options_django', sys.exc_info()[1] or Exception())
    signals.got_request_exception.connect(options_exception, weak=False)

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args): pass
        def get_stderr(self):
            import io
            return io.StringIO()  # Never emit WSGI tracebacks containing request data.

    def app(environ, start_response):
        if environ.get('HTTP_HOST') != '127.0.0.1:'+str(server.server_port) or environ.get('REQUEST_METHOD') == 'CONNECT':
            start_response('403 Forbidden', [('Content-Type', 'text/plain')]); return [b'Blocked']
        environ['REMOTE_ADDR'] = '127.8.'+str(int(scenario.marker[:2],16))+'.1'
        url = environ.get('PATH_INFO', '/')
        if url.startswith('/api/'):
            if url.endswith('/auth/challenges/'):
                scenario.clock_seconds += 61
            options_request = url == '/api/v1/dic/participant/auth/options/'
            try:
                chunks = list(django_app(environ, start_response))
            except Exception as error:
                if options_request: record_browser_failure(receipt, 'options_wsgi_response', error)
                raise
            try:
                scenario.deliver_queued()
            except Exception as error:
                if options_request: record_browser_failure(receipt, 'options_postprocessing', error)
                raise
            if url == '/api/v1/dic/orders/' and environ['REQUEST_METHOD'] == 'POST':
                body = json.loads(b''.join(chunks))
                if 'order_id' in body and 'access_token' in body:
                    scenario.last_booking = {'client': scenario.client(), 'order': body['order_id'], 'token': body['access_token'], 'email': scenario.owner}
            return chunks
        import mimetypes
        candidate = (dist / url.lstrip('/')).resolve()
        if not candidate.is_relative_to(dist.resolve()):
            start_response('404 Not Found', []); return [b'']
        if not candidate.is_file(): candidate = dist / 'index.html'
        start_response('200 OK', [('Content-Type', mimetypes.guess_type(str(candidate))[0] or 'application/octet-stream'), ('Cache-Control', 'no-store')])
        return [candidate.read_bytes()]

    server = make_server('127.0.0.1', 0, app, handler_class=QuietHandler)
    allowed_http.add(server.server_port)
    origin = 'http://127.0.0.1:'+str(server.server_port)
    settings.CSRF_TRUSTED_ORIGINS = [origin]

    def serve():
        connection = connections['default']
        try:
            identity(connection, port)
            with rollback_run(connection, receipt, path):
                scenario.seed()
                ready.put(True)
                while not stopped.is_set():
                    try:
                        function, answer = jobs.get_nowait()
                    except queue.Empty:
                        server.handle_request()
                    else:
                        try: answer.put((True, function()))
                        except Exception: answer.put((False, None)); raise
                receipt['checks'].extend(scenario.checks)
        except Exception as error:
            record_browser_failure(receipt, 'backend_failure', error)
            failures.put(True); ready.put(False)
        finally:
            connection.close()

    server.timeout = 0.1
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    def task(function):
        answer = queue.Queue(); jobs.put((function, answer))
        success, result = answer.get(timeout=30)
        require(success, 'Browser fixture task failed.')
        return result

    try:
        stage = 'backend_start'; receipt['browser_stage'] = stage
        require(ready.get(timeout=30), 'Guarded browser backend initialization failed.')
        stage = 'playwright_start'; receipt['browser_stage'] = stage
        with sync_playwright() as playwright:
            stage = 'chromium_launch'; receipt['browser_stage'] = stage
            browser = playwright.chromium.launch(headless=True,
                proxy={'server': origin, 'bypass': '127.0.0.1,localhost'},
                args=['--disable-background-networking', '--disable-component-update', '--disable-sync',
                    '--no-first-run', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'])
            stage = 'browser_context'; receipt['browser_stage'] = stage
            context = browser.new_context(service_workers='block')
            context.set_default_timeout(10000)
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
            page = context.new_page()
            def delivery_response(response):
                if response.url != origin+'/api/v1/dic/participant/auth/options/':
                    return
                probe = {'http_status': response.status}
                try:
                    data = response.json()
                    channels = data.get('channels') if isinstance(data, dict) else None
                    probe['valid_channels_shape'] = isinstance(channels, list)
                    if isinstance(channels, list):
                        probe['email_available'] = any(isinstance(channel, dict)
                            and channel.get('value') == 'email' and channel.get('available') is True for channel in channels)
                except Exception:
                    probe['response_unreadable'] = True
                receipt['otp_delivery_probe'] = probe
            page.on('response', delivery_response)
            stage = 'registration_navigation'; receipt['browser_stage'] = stage
            page.goto(origin+'/dic/register')
            for index in range(2):
                stage = 'participant_form'; receipt['browser_stage'] = stage
                if index:
                    page.get_by_role('button', name='+ Add participant', exact=True).click()
                for name, value in (('fullName', 'SYNTHETIC '+scenario.marker+' browser'+str(index)),
                        ('address', 'Synthetic acceptance only'), ('phone', '08012345678'),
                        ('email', scenario.marker+'.browser'+str(index)+'@example.test')):
                    page.locator('input[name="'+name+'"]').fill(value)
                for name, value in (('ageChoice', 'minor'), ('academicStatus', 'Not Currently in School'),
                        ('occupation', 'None'), ('maritalStatus', 'None')):
                    page.locator('select[name="'+name+'"]').select_option(value, force=True)
                page.locator('input[name="dob"]').fill(f'{scenario.clock_start.year-10-index*2}-01-01')
                page.locator('input[name="sex"][value="Male"]').check()
                page.locator('input[name="categoryId"][value="'+str(scenario.category.pk)+'"]').check(force=True)
                page.get_by_role('button', name=re.compile('^Continue to summary')).click()
            stage = 'checkout'; receipt['browser_stage'] = stage
            page.get_by_role('button', name=re.compile('^Continue to checkout')).click()
            page.get_by_label('Primary camper or guardian name', exact=True).fill('SYNTHETIC browser guardian')
            page.get_by_label('Booking email', exact=True).fill(scenario.owner)
            page.locator('input[autocomplete="new-password" ]').nth(0).fill(scenario.password)
            page.locator('input[autocomplete="new-password" ]').nth(1).fill(scenario.password)
            with page.expect_response(lambda response: response.url == origin+'/api/v1/dic/orders/' and response.status == 201):
                page.get_by_role('button', name=re.compile('^Create order and continue to payment')).click()
            booking = task(lambda: scenario.last_booking)
            require(booking is not None, 'Browser registration was not captured.')
            stage = 'payment_verification'; receipt['browser_stage'] = stage
            task(lambda: scenario.settle(booking))
            scenario.checks.append('browser_primary_contact_multichild_registration_verified_mock_payment')
            stage = 'portal_navigation'; receipt['browser_stage'] = stage
            token = task(lambda: scenario.verification_link(scenario.owner))
            page.goto(origin+'/dic/participant#verify-email='+token)
            stage = 'account_activation'; receipt['browser_stage'] = stage
            page.get_by_role('button', name='Confirm email ownership', exact=True).click()
            page.get_by_text('Email verified. Sign in with your password once payment is confirmed.', exact=True).wait_for()
            page.get_by_label('Email or username', exact=True).fill(scenario.owner)
            page.locator('input[autocomplete="current-password"]').fill(scenario.password)
            page.get_by_role('button', name='Sign In', exact=True).click()
            page.get_by_role('heading', name='Sign-in settings', exact=True).wait_for()
            stage = 'logout'; receipt['browser_stage'] = stage
            page.goto(origin+'/dic/participant?view=profile')
            page.get_by_role('button', name='Secure logout', exact=True).click()
            stage = 'password_login'; receipt['browser_stage'] = stage
            page.get_by_label('Email or username', exact=True).fill(scenario.owner)
            page.locator('input[autocomplete="current-password"]').fill(scenario.password)
            page.get_by_role('button', name='Sign In', exact=True).click()
            page.get_by_role('heading', name='Sign-in settings', exact=True).wait_for()
            stage = 'camper_switch'; receipt['browser_stage'] = stage
            selector = page.locator('.cp-camper-select select')
            require(selector.locator('option').count() == 2, 'Browser guardian camper scope mismatch.')
            selector.select_option(index=1)
            require(selector.evaluate('(element) => element.selectedIndex') == 1, 'Browser camper switching failed.')
            require(page.get_by_role('button', name='Continue with Google', exact=True).count() == 0, 'Google controls are not hidden.')
            scenario.checks.append('browser_registration_password_email_link_logout_login_guardian_switching')
            stage = 'browser_cleanup'; receipt['browser_stage'] = stage
            context.close(); browser.close()
    except Exception as error:
        diagnostic = record_browser_failure(receipt, stage, error)
        raise StopAcceptance('Browser acceptance failed: stage='+diagnostic['stage']+
            ' category='+diagnostic['category']+' hint='+diagnostic['hint']) from None
    finally:
        stopped.set()
        thread.join(timeout=30)
        server.server_close()
        signals.request_started.connect(close_old_connections)
        signals.request_finished.connect(close_old_connections)
        signals.got_request_exception.disconnect(options_exception)
        require(not thread.is_alive() and failures.empty(), 'Browser rollback failed or could not be verified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'integration', 'browser'))
    parser.add_argument('--database', required=True, choices=(DATABASE,))
    parser.add_argument('--confirm-demo-writes', action='store_true')
    parser.add_argument('--diagnose-otp-options', action='store_true', help='Database-free endpoint probes during read-only preflight only.')
    args = parser.parse_args()
    writing = args.command != 'preflight'
    require(not args.diagnose_otp_options or not writing, 'OTP options diagnosis is preflight-only.')
    require(not writing or args.confirm_demo_writes, 'Writing commands require --confirm-demo-writes.')
    port, marker = configure(args.database, writing)
    allowed_http = set()
    receipt = {'version': 1, 'run': marker, 'command': args.command, 'database': DATABASE,
        'status': 'started', 'cleanup': 'no_database_writes', 'fixtures': {}, 'checks': []}
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    path = RECEIPTS / ('phase3-'+marker+'.json')
    require(not path.exists(), 'Receipt collision.')
    with guards(port, allowed_http, allow_browser=args.command == 'browser') as stack:
        import django
        django.setup()
        from django.db import connection, connections, transaction
        from django.conf import settings
        require(settings.DEBUG and settings.DATABASES['default']['NAME'] == DATABASE, 'Unsafe resolved settings.')
        settings.DATABASES['default']['OPTIONS'] = {'connect_timeout': 5,
            'options': '-c statement_timeout=10000 -c default_transaction_read_only=on'}
        try:
            with transaction.atomic():
                receipt['identity'] = identity(connection, port, readonly=True)
                receipt['schema'] = schema(connection)
                receipt['fixture_requirements'] = fixture_requirements()
            if args.diagnose_otp_options:
                receipt['otp_options_diagnosis'] = diagnose_otp_options()
                print('OTP options diagnosis:', json.dumps(receipt['otp_options_diagnosis'], sort_keys=True))
                require(all(item['passed'] for item in receipt['otp_options_diagnosis'].values()), 'OTP options independent probe failed; see sanitized receipt.')
            receipt['browser_prerequisites'] = {'frontend_build': (ROOT/'dawana-platform/dist/index.html').is_file(),
                'playwright_package': importlib.util.find_spec('playwright') is not None}
            if writing:
                connections.close_all()
                settings.DATABASES['default']['OPTIONS']['options'] = '-c statement_timeout=10000 -c default_transaction_read_only=off'
                if args.command == 'integration':
                    with ExitStack() as providers:
                        scenario = Scenario(marker); scenario.install(providers)
                        identity(connection, port)
                        with rollback_run(connection, receipt, path):
                            scenario.seed(); scenario.integration()
                            connection.check_constraints()
                            receipt['checks'].extend(scenario.checks)
                else:
                    require_browser_prerequisites(receipt['browser_prerequisites'])
                    # API acceptance and browser acceptance each use their own rollback.
                    with ExitStack() as providers:
                        scenario = Scenario(marker); scenario.install(providers)
                        with rollback_run(connection, receipt, path):
                            scenario.seed(); scenario.integration(); connection.check_constraints()
                            receipt['checks'].extend(scenario.checks)
                    with ExitStack() as providers:
                        scenario = Scenario(uuid.uuid4().hex); scenario.install(providers)
                        connections.close_all()
                        browser_run(scenario, receipt, path, port, allowed_http)
            receipt['status'] = 'passed'
        except Exception as error:
            receipt['status'] = 'failed'
            if args.command == 'browser' and not receipt.get('browser_failures'):
                diagnostic = record_browser_failure(receipt, receipt.get('browser_stage', 'unknown'), error)
                raise StopAcceptance('Browser acceptance failed: stage='+diagnostic['stage']+
                    ' category='+diagnostic['category']+' hint='+diagnostic['hint']) from None
            raise
        finally:
            connections.close_all()
            write_receipt(path, receipt)
    print('PASS:', args.command, DATABASE, 'receipt:', path.relative_to(ROOT))


if __name__ == '__main__':
    try:
        main()
    except StopAcceptance as error:
        # All StopAcceptance messages above are fixed, non-sensitive diagnostics.
        print('STOP:', str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('STOP: acceptance failed; no exception text or traceback is disclosed.', file=sys.stderr)
        sys.exit(1)
