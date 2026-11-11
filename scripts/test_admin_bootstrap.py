"""Synthetic initial-admin tests: in-memory SQLite only, no dotenv or network."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def forbidden(*args, **kwargs):
    raise RuntimeError('External connections are forbidden in bootstrap tests.')


socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
POSTGRES = os.environ.get('DAWANA_ADMIN_BOOTSTRAP_TEST_POSTGRES') == '1'
TEST_DATABASE = ':memory:'
PG_LOCAL = None
if POSTGRES:
    if sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('PostgreSQL tests require an ephemeral Linux Actions job.')
    if any(value for name, value in os.environ.items() if name.startswith(('RECOVERY_', 'DJANGO_BOOTSTRAP_'))
           or name in ('DATABASE_URL', 'DJANGO_SETTINGS_MODULE')):
        raise RuntimeError('Production configuration is forbidden in PostgreSQL tests.')
    for name in list(os.environ):
        if name.startswith('PG'):
            del os.environ[name]
    import psycopg
    from psycopg import sql
    directory = Path(os.environ['RUNNER_TEMP']) / 'admin-bootstrap-ci'
    PG_LOCAL = dict(host='127.0.0.1', port=55439, user='bootstrap_ci', password='synthetic-ci-only',
                    sslmode='verify-full', sslrootcert=str(directory / 'server.crt'), connect_timeout=3)
    TEST_DATABASE = 'test_admin_bootstrap_' + uuid.uuid4().hex
    with psycopg.connect(dbname='postgres', **PG_LOCAL, autocommit=True) as admin:
        identity = admin.execute("SELECT current_user, current_setting('data_directory'), "
            "current_setting('server_version_num')::integer / 10000, system_identifier::text "
            "FROM pg_control_system()").fetchone()
        if identity != ('bootstrap_ci', str(directory / 'data'), 18,
                        (directory / 'cluster-id').read_text().strip()):
            raise RuntimeError('Disposable PostgreSQL cluster identity mismatch.')
        admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(TEST_DATABASE)))
    database = dict(ENGINE='django.db.backends.postgresql', NAME=TEST_DATABASE, HOST='127.0.0.1', PORT='55439',
                    USER='bootstrap_ci', PASSWORD='synthetic-ci-only', CONN_MAX_AGE=0,
                    OPTIONS=dict(sslmode='verify-full', sslrootcert=str(directory / 'server.crt'), connect_timeout=3))
else:
    database = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
from django.conf import settings
settings.configure(SECRET_KEY='synthetic-only-bootstrap-tests', USE_TZ=True,
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'accounts'],
    AUTH_USER_MODEL='accounts.User',
    DATABASES={'default': database},
    PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'],
    AUTH_PASSWORD_VALIDATORS=[
        {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
        {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
        {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
        {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    ])
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction

SPEC = importlib.util.spec_from_file_location('admin_bootstrap', ROOT / 'backend/config/github_admin_bootstrap.py')
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)
User = get_user_model()
PASSWORD = 'Cedar-Lantern!River-84-Synthetic'


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.settings_dict['NAME'] != TEST_DATABASE or connection.vendor != ('postgresql' if POSTGRES else 'sqlite'):
            raise RuntimeError('Only the exact disposable synthetic database is allowed.')
        with connection.schema_editor() as editor:
            for model in (ContentType, Permission, Group, User):
                editor.create_model(model)

    def setUp(self):
        User.objects.all().delete()

    def create(self, username='synthetic-owner'):
        candidate = bootstrap.prepare_user(User, username, PASSWORD)
        with transaction.atomic():
            bootstrap.insert_initial_user(User, 'default', candidate)
        return candidate

    def test_new_account_is_hashed_active_staff_and_superuser(self):
        user = self.create()
        saved = User.objects.get(pk=user.pk)
        self.assertTrue(saved.is_active and saved.is_staff and saved.is_superuser)
        self.assertNotEqual(saved.password, PASSWORD)
        self.assertTrue(saved.check_password(PASSWORD))
        self.assertEqual(User.objects.count(), 1)

    def test_existing_username_is_never_reset_or_elevated_even_case_variant(self):
        original = User.objects.create_user(username='SYNTHETIC-OWNER', password=PASSWORD)
        before = (original.password, original.is_active, original.is_staff, original.is_superuser)
        with self.assertRaises(bootstrap.BootstrapStop):
            self.create()
        original.refresh_from_db()
        self.assertEqual((original.password, original.is_active, original.is_staff, original.is_superuser), before)
        self.assertEqual(User.objects.count(), 1)

    def test_initial_superuser_prevents_second_bootstrap_under_another_name(self):
        self.create()
        with self.assertRaises(bootstrap.BootstrapStop):
            self.create('another-owner')
        self.assertEqual(User.objects.count(), 1)

    def test_rerun_refuses_without_changing_existing_hash(self):
        user = self.create()
        before = user.password
        with self.assertRaises(bootstrap.BootstrapStop):
            self.create()
        self.assertEqual(User.objects.get(pk=user.pk).password, before)

    def test_failure_rolls_back_insert(self):
        candidate = bootstrap.prepare_user(User, 'rollback-owner', PASSWORD)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                bootstrap.insert_initial_user(User, 'default', candidate)
                raise RuntimeError('Synthetic rollback')
        self.assertFalse(User.objects.exists())

    def test_invalid_credentials_do_not_create_accounts(self):
        for username, password in (('', PASSWORD), (' owner ', PASSWORD), ('bad/name', PASSWORD),
                                   ('valid-owner', ''), ('valid-owner', '1234567890123456')):
            with self.subTest(username=username), self.assertRaises(bootstrap.BootstrapStop):
                bootstrap.prepare_user(User, username, password)
        self.assertFalse(User.objects.exists())

    def test_manual_main_first_attempt_and_confirmation_are_required(self):
        valid = dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                     GITHUB_RUN_ATTEMPT='1', BOOTSTRAP_APPROVAL='CREATE INITIAL SUPERUSER')
        bootstrap.validate_request(valid)
        for key, value in (('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/other'),
                           ('GITHUB_RUN_ATTEMPT', '2'), ('BOOTSTRAP_APPROVAL', '')):
            with self.subTest(key=key), self.assertRaises(bootstrap.BootstrapStop):
                bootstrap.validate_request({**valid, key: value})

    def test_database_identity_and_actual_tls_are_checked(self):
        expected = dict(host='synthetic.render.com', schema='public', cluster='123')
        actual = ('dawana_db', 'dawana_db_user', 'dawana_db_user', 'public', '123', 'on')
        cursor = Mock()
        cursor.fetchone.side_effect = [actual, (True,)]
        bootstrap.verify_connection(cursor, expected, 'on')
        for responses in ([(*actual[:4], '456', 'on')], [actual, (False,)], [actual, None]):
            cursor.fetchone.side_effect = responses
            with self.assertRaises(bootstrap.BootstrapStop):
                bootstrap.verify_connection(cursor, expected, 'on')

    def test_configured_identity_tls_and_schema_mismatches_refuse(self):
        expected = dict(host='synthetic.render.com', schema='public', cluster='123')
        config = dict(ENGINE='django.db.backends.postgresql', NAME='dawana_db', USER='dawana_db_user',
                      HOST=expected['host'], PORT='5432', OPTIONS={'sslmode': 'verify-full'})
        render = SimpleNamespace(SETTINGS_MODULE='config.settings.render')
        bootstrap.verify_config(render, SimpleNamespace(settings_dict=config), expected)
        for change in ({'HOST': 'other.render.com'}, {'NAME': 'other'}, {'USER': 'other'}, {'PORT': '55439'},
                       {'ENGINE': 'django.db.backends.sqlite3'}, {'OPTIONS': {'sslmode': 'require'}},
                       {'OPTIONS': {'sslmode': 'disable'}}):
            with self.assertRaises(bootstrap.BootstrapStop):
                bootstrap.verify_config(render, SimpleNamespace(settings_dict={**config, **change}), expected)
        with self.assertRaises(bootstrap.BootstrapStop):
            bootstrap.verify_config(SimpleNamespace(SETTINGS_MODULE='config.settings.development'),
                                    SimpleNamespace(settings_dict=config), expected)
        cursor = Mock()
        cursor.fetchone.return_value = ('wrong_schema',)
        with self.assertRaises(bootstrap.BootstrapStop):
            bootstrap.verify_user_table(cursor, connection, User, 'public')

    def test_error_reports_never_echo_credentials_or_arbitrary_messages(self):
        private = 'postgresql://private_user:private_password@private-host.invalid/private_db'
        for error in (RuntimeError(private), bootstrap.BootstrapStop(private)):
            self.assertEqual(bootstrap.safe_report(error), {'admin_bootstrap': 'STOP', 'category': 'operation_failed'})
        report = bootstrap.safe_report(bootstrap.BootstrapStop('requested_username_exists'))
        self.assertEqual(report['category'], 'requested_username_exists')

    def test_database_connection_failure_is_sanitized_and_creates_nothing(self):
        from django.db import OperationalError
        private = 'synthetic-private-password synthetic-host.invalid'
        output, errors = io.StringIO(), io.StringIO()
        def fail():
            print(private)
            print(private, file=sys.stderr)
            raise OperationalError(private)
        with patch.object(bootstrap, 'run', side_effect=fail), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(bootstrap.execute(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'admin_bootstrap': 'STOP', 'category': 'database_operation_failed'})
        self.assertEqual(errors.getvalue(), '')
        self.assertNotIn(private, output.getvalue())
        self.assertFalse(User.objects.exists())

    def test_each_write_gate_failure_prevents_insert(self):
        guards = ('verify_config', 'verify_connection', 'verify_user_table', 'acquire_bootstrap_locks')
        for failed in guards:
            fake = SimpleNamespace(alias='default', cursor=MagicMock())
            with self.subTest(gate=failed), contextlib.ExitStack() as stack:
                for name in guards:
                    stack.enter_context(patch.object(bootstrap, name,
                        side_effect=bootstrap.BootstrapStop('connected_identity_mismatch') if name == failed else None))
                insert = stack.enter_context(patch.object(bootstrap, 'insert_initial_user'))
                with self.assertRaises(bootstrap.BootstrapStop):
                    bootstrap.write_initial_user(None, fake, {'schema': 'public'}, User, Mock())
                insert.assert_not_called()

    def test_every_connected_identity_component_and_transaction_mode_are_required(self):
        expected = dict(host='synthetic.render.com', schema='public', cluster='123')
        actual = ['dawana_db', 'dawana_db_user', 'dawana_db_user', 'public', '123', 'off']
        for index in range(len(actual)):
            cursor = Mock()
            wrong = actual.copy()
            wrong[index] = 'wrong'
            cursor.fetchone.return_value = tuple(wrong)
            with self.subTest(component=index), self.assertRaises(bootstrap.BootstrapStop):
                bootstrap.verify_connection(cursor, expected, 'off')
            self.assertEqual(cursor.execute.call_count, 1)

    def test_workflow_is_manual_protected_and_tests_precede_secret_job(self):
        workflow = json.loads((ROOT / '.github/workflows/production-admin-bootstrap.yml').read_text())
        self.assertEqual(workflow['name'], 'Production Django Admin Bootstrap')
        self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        jobs = workflow['jobs']
        self.assertNotIn('environment', jobs['validation'])
        self.assertNotIn('secrets.', json.dumps(jobs['validation']))
        self.assertEqual(jobs['bootstrap']['needs'], 'validation')
        self.assertEqual(jobs['bootstrap']['environment'], 'production-initialize')
        self.assertIn('refs/heads/main', jobs['bootstrap']['if'])
        commands = '\n'.join(step.get('run', '') for step in jobs['bootstrap']['steps'])
        self.assertNotIn('manage.py', commands)
        self.assertIn('github_admin_bootstrap.py', commands)

    def test_independent_validation_never_calls_production_bootstrap(self):
        workflow = json.loads((ROOT / '.github/workflows/admin-bootstrap-validation.yml').read_text())
        self.assertEqual(set(workflow['on']), {'workflow_dispatch', 'pull_request'})
        self.assertNotIn('secrets.', json.dumps(workflow))
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertNotIn('upload-artifact', json.dumps(workflow))
        for job in workflow['jobs'].values():
            self.assertNotIn('environment', job)
            commands = '\n'.join(step.get('run', '') for step in job['steps'])
            self.assertIn('scripts/test_admin_bootstrap.py', commands)
            self.assertNotIn('config/github_admin_bootstrap.py', commands)


if POSTGRES:
    class PostgresConcurrencyTests(unittest.TestCase):
        def setUp(self):
            User.objects.all().delete()

        def race(self, names):
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            from django.db import connections, close_old_connections
            ready = Barrier(2)
            def worker(name):
                close_old_connections()
                try:
                    candidate = bootstrap.prepare_user(User, name, PASSWORD)
                    ready.wait(timeout=15)
                    with transaction.atomic():
                        local = connections['default']
                        with local.cursor() as cursor:
                            cursor.execute("SET LOCAL statement_timeout='5000'")
                            cursor.execute("SET LOCAL lock_timeout='1000'")
                            bootstrap.verify_encrypted_connection(cursor)
                            bootstrap.acquire_bootstrap_locks(cursor, local, User)
                        bootstrap.insert_initial_user(User, 'default', candidate)
                    return 'CREATED'
                except bootstrap.BootstrapStop as exc:
                    return bootstrap.safe_report(exc)['category']
                finally:
                    connections['default'].close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(worker, name) for name in names]
                results = [future.result(timeout=25) for future in futures]
            self.assertEqual(results.count('CREATED'), 1, results)
            self.assertEqual(User.objects.count(), 1)
            self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)

        def test_concurrent_different_usernames_create_exactly_one_admin(self):
            self.race(['concurrent-owner-one', 'concurrent-owner-two'])

        def test_concurrent_case_variants_create_exactly_one_admin(self):
            self.race(['Concurrent-Owner', 'concurrent-owner'])

        def test_real_tls_and_plaintext_rejection(self):
            with connection.cursor() as cursor:
                bootstrap.verify_encrypted_connection(cursor)
            with psycopg.connect(dbname=TEST_DATABASE, **{**PG_LOCAL, 'sslmode': 'disable'}) as plain:
                with plain.cursor() as cursor, self.assertRaises(bootstrap.BootstrapStop):
                    bootstrap.verify_encrypted_connection(cursor)

        def test_real_connection_failure_does_not_create_user(self):
            from psycopg import OperationalError
            with self.assertRaises(OperationalError):
                psycopg.connect(dbname=TEST_DATABASE, **{**PG_LOCAL, 'port': 55440, 'connect_timeout': 1})
            self.assertFalse(User.objects.exists())

        def test_untrusted_server_certificate_is_rejected(self):
            with self.assertRaises(psycopg.OperationalError):
                psycopg.connect(dbname=TEST_DATABASE,
                    **{**PG_LOCAL, 'sslrootcert': '/etc/ssl/certs/ca-certificates.crt'})
            self.assertFalse(User.objects.exists())


if __name__ == '__main__':
    try:
        result = unittest.main(exit=False).result
        status = 0 if result.wasSuccessful() and result.testsRun > 0 else 1
    finally:
        if POSTGRES:
            from django.db import connections
            connections.close_all()
            with psycopg.connect(dbname='postgres', **PG_LOCAL, autocommit=True) as admin:
                admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s', [TEST_DATABASE])
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(TEST_DATABASE)))
    sys.exit(status)
