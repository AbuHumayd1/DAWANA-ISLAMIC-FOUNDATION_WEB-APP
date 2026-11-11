"""Manual initial-admin bootstrap only. Never imported by application startup."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys


class BootstrapStop(Exception):
    pass


def require(condition, category):
    if not condition:
        raise BootstrapStop(category)


def validate_request(environ):
    require(environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and environ.get('GITHUB_REF') == 'refs/heads/main'
            and environ.get('GITHUB_RUN_ATTEMPT') == '1', 'manual_main_first_attempt_required')
    require(environ.get('BOOTSTRAP_APPROVAL') == 'CREATE INITIAL SUPERUSER', 'explicit_approval_required')


def expected_identity(environ):
    host = environ.get('RECOVERY_EXPECTED_HOST', '')
    schema = environ.get('RECOVERY_EXPECTED_SCHEMA', '')
    cluster = environ.get('RECOVERY_EXPECTED_CLUSTER_ID', '')
    require(bool(host) and bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema))
            and bool(re.fullmatch(r'[0-9]+', cluster)), 'expected_identity_required')
    return dict(host=host, schema=schema, cluster=cluster)


def verify_config(settings, connection, expected):
    config = connection.settings_dict
    require(settings.SETTINGS_MODULE == 'config.settings.render'
            and config.get('ENGINE') == 'django.db.backends.postgresql'
            and (config.get('NAME'), config.get('USER'), str(config.get('PORT') or '5432'), config.get('HOST'))
            == ('dawana_db', 'dawana_db_user', '5432', expected['host'])
            and config.get('OPTIONS', {}).get('sslmode') == 'verify-full', 'configured_identity_or_tls_mismatch')


def verify_connection(cursor, expected, read_only):
    # Identical database/role/schema/cluster binding to the recovery gate.
    cursor.execute("""
        SELECT current_database(), session_user, current_user, current_schema(),
               system_identifier::text, current_setting('transaction_read_only')
        FROM pg_catalog.pg_control_system()
    """)
    require(cursor.fetchone() == ('dawana_db', 'dawana_db_user', 'dawana_db_user',
                                 expected['schema'], expected['cluster'], read_only), 'connected_identity_mismatch')
    verify_encrypted_connection(cursor)


def verify_encrypted_connection(cursor):
    cursor.execute('SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid()')
    require(cursor.fetchone() == (True,), 'encrypted_connection_required')


def verify_user_table(cursor, connection, model, schema):
    cursor.execute("""
        SELECT n.nspname FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE c.oid=pg_catalog.to_regclass(%s)
    """, [connection.ops.quote_name(model._meta.db_table)])
    require(cursor.fetchone() == (schema,), 'user_table_schema_mismatch')


def prepare_user(model, username, password):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    require(isinstance(username, str) and bool(username) and username == username.strip(), 'invalid_admin_username')
    require(isinstance(password, str) and 16 <= len(password) <= 128, 'invalid_admin_password')
    user = model(**{model.USERNAME_FIELD: username}, is_active=True, is_staff=True, is_superuser=True)
    try:
        validate_password(password, user=user)
        user.set_password(password)  # Configured Django hashers; no raw SQL credentials.
        user.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        raise BootstrapStop('admin_credentials_validation_failed') from None
    require(user.has_usable_password() and user.password != password, 'password_hashing_failed')
    return user


def insert_initial_user(model, alias, user):
    """Caller holds the transaction, advisory lock and user-table write lock."""
    manager = model._default_manager.db_manager(alias)
    require(not manager.filter(**{model.USERNAME_FIELD + '__iexact': user.get_username()}).exists(),
            'requested_username_exists')
    require(not manager.filter(is_superuser=True).exists(), 'initial_superuser_already_exists')
    user.save(using=alias, force_insert=True)
    saved = manager.get(pk=user.pk)
    require(saved.is_active and saved.is_staff and saved.is_superuser and saved.has_usable_password()
            and saved.password == user.password and saved.get_username() == user.get_username(),
            'created_admin_verification_failed')


def acquire_bootstrap_locks(cursor, connection, model):
    cursor.execute('SELECT pg_catalog.pg_try_advisory_xact_lock(184740211, 2)')
    require(cursor.fetchone() == (True,), 'another_recovery_operation_is_running')
    cursor.execute('LOCK TABLE ' + connection.ops.quote_name(model._meta.db_table)
                   + ' IN SHARE ROW EXCLUSIVE MODE')


def write_initial_user(settings, connection, expected, model, user):
    from django.db import transaction
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            # Session default stays read-only; only this transaction may write.
            cursor.execute('SET TRANSACTION READ WRITE')
            verify_config(settings, connection, expected)
            verify_connection(cursor, expected, 'off')
            verify_user_table(cursor, connection, model, expected['schema'])
            acquire_bootstrap_locks(cursor, connection, model)
        insert_initial_user(model, connection.alias, user)


def run():
    validate_request(os.environ)  # Reject unsupported dispatches before loading secrets/settings.
    expected = expected_identity(os.environ)
    username = os.environ.pop('DJANGO_BOOTSTRAP_ADMIN_USERNAME', '')
    password = os.environ.pop('DJANGO_BOOTSTRAP_ADMIN_PASSWORD', '')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Reuse the exact reviewed Render loader; never invent a separate DATABASE_URL.
    from config.github_schema_recovery import initialize_environment
    # Its masking directives contain values; discard them here. This script emits
    # fixed result categories only, never credentials, validation text or tracebacks.
    with contextlib.redirect_stdout(io.StringIO()):
        settings, connection, _, _ = initialize_environment()
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django.db.migrations.executor import MigrationExecutor

    try:
        verify_config(settings, connection, expected)
        model = get_user_model()
        with transaction.atomic(using=connection.alias):
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION READ ONLY')
                verify_connection(cursor, expected, 'on')
                verify_user_table(cursor, connection, model, expected['schema'])
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            require(not executor.loader.detect_conflicts()
                    and not executor.migration_plan(executor.loader.graph.leaf_nodes()), 'schema_not_fully_initialized')
        user = prepare_user(model, username, password)  # Hash/validate BEFORE locking the table.
        password = None
        write_initial_user(settings, connection, expected, model, user)
        return {'admin_bootstrap': 'CREATED'}
    finally:
        password = None
        connection.close()


def safe_report(exc):
    allowed = {
        'manual_main_first_attempt_required', 'explicit_approval_required', 'expected_identity_required',
        'configured_identity_or_tls_mismatch', 'connected_identity_mismatch', 'encrypted_connection_required',
        'user_table_schema_mismatch', 'invalid_admin_username', 'invalid_admin_password',
        'admin_credentials_validation_failed', 'password_hashing_failed', 'requested_username_exists',
        'initial_superuser_already_exists', 'created_admin_verification_failed', 'schema_not_fully_initialized',
        'another_recovery_operation_is_running',
    }
    category = str(exc) if isinstance(exc, BootstrapStop) and str(exc) in allowed else 'operation_failed'
    if category == 'operation_failed':
        try:
            from django.db import OperationalError
            if isinstance(exc, OperationalError):
                category = 'database_operation_failed'
        except ImportError:
            pass
    return {'admin_bootstrap': 'STOP', 'category': category}


def execute():
    # Even third-party loggers/validators must not expose configuration or values.
    try:
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = run()
            require(result == {'admin_bootstrap': 'CREATED'}, 'unexpected_result')
    except BaseException as exc:
        result = safe_report(exc)
    print(json.dumps(result), flush=True)
    return 0 if result == {'admin_bootstrap': 'CREATED'} else 1


if __name__ == '__main__':
    sys.exit(execute())
