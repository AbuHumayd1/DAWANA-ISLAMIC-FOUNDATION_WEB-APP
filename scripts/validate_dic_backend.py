"""Local-only DIC validation. Never drops a database or contacts R2/Paystack."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
import unittest
from datetime import datetime, timezone
from urllib.parse import quote
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
LABELS = [
    'dic.test_promotions', 'dic.test_memories', 'dic.test_videos', 'dic.test_showcase',
    'dic.tests.RegistrationApiTests', 'dic.tests.PaymentApiTests',
    'dic.tests.ConcurrentPaymentSettlementTests', 'dic.tests.PaystackClientTests',
    'dic.test_staging_tester_access',
]


class ValidationStop(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ValidationStop(message)


def missing_test_labels(labels, observed, skipped):
    return [label for label in labels if not any(
        (test_id == label or test_id.startswith(label + '.')) and test_id not in skipped
        for test_id in observed)]


def genuine_mp4(ffprobe):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import override_settings
    from dic.promo_storage import validate_mp4, PrivatePromoStorage
    ffmpeg = str(Path(ffprobe).with_name('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'))
    if not Path(ffmpeg).is_file():
        ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg, 'ffmpeg companion executable is missing')
    with tempfile.TemporaryDirectory(prefix='dawana-synthetic-video-') as directory:
        video = Path(directory) / 'synthetic.mp4'
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=green:s=320x180:r=10', '-t', '1', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', str(video)],
                       capture_output=True, check=True, timeout=30)
        payload = video.read_bytes()
        with override_settings(DIC_FFPROBE_BINARY=ffprobe, DEBUG=True,
                               DIC_MEMORY_STORAGE='local', DIC_MEMORY_LOCAL_ROOT=directory):
            upload = SimpleUploadedFile('synthetic.mp4', payload, content_type='video/mp4')
            validate_mp4(upload)
            storage = PrivatePromoStorage()
            name = storage.save('synthetic.mp4', upload)
            with storage.open(name) as handle:
                require(handle.read() == payload, 'Synthetic local MP4 round trip failed')
    return 'PASS: genuine H.264 MP4 validation and private local storage round trip'


def main(args, report):
    require(not (args.operations_scoring and (args.housing_only or args.ids_only or args.phase2_and3 or args.operations_feedback)), 'Choose only one focused suite option')
    require(not (args.operations_feedback and (args.housing_only or args.ids_only or args.phase2_and3)), 'Choose only one focused suite option')
    if args.ids_only or args.phase2_and3:
        import importlib
        for module in ('reportlab', 'pypdf', 'fitz', 'cv2', 'numpy', 'qrcode'):
            try:
                importlib.import_module(module)
            except ImportError:
                raise ValidationStop('Missing ID validation dependency: ' + module + '; install backend/requirements-test-ids.txt in the existing virtual environment.') from None
    import environ
    import psycopg
    from psycopg import sql
    environ.Env.read_env(BACKEND / '.env')
    env = environ.Env()
    # Keep these values in memory only; never print a connection string.
    if env('DATABASE_URL', default=''):
        configured = env.db_url('DATABASE_URL')
        require(configured.get('ENGINE') == 'django.db.backends.postgresql', 'PostgreSQL required')
        connection = dict(host=configured.get('HOST') or '127.0.0.1',
                          port=configured.get('PORT') or 5432,
                          user=configured.get('USER') or '', password=configured.get('PASSWORD') or '')
    else:
        connection = dict(host=env('DB_HOST', default='127.0.0.1'), port=env('DB_PORT', default='5432'),
                          user=env('DB_USER'), password=env('DB_PASSWORD', default=''))
    require(connection['host'].lower() in ('127.0.0.1', 'localhost', '::1'),
            'Refusing a non-loopback database host; use local test credentials')
    connection['connect_timeout'] = 5
    if connection['password']:
        secret_values.append(connection['password'])
    secret_values.extend(value for key, value in os.environ.items()
                         if any(token in key for token in ('PASSWORD', 'SECRET', 'TOKEN', 'ACCESS_KEY', 'DATABASE_URL')) and value)
    report['phase'] = 'read-only existing test database inspection'
    print('Inspecting test_dawana_dev read-only; no records will be changed.', flush=True)
    with psycopg.connect(**connection, dbname='postgres', autocommit=True,
                         options='-c default_transaction_read_only=on') as conn:
        existing = conn.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s)', ('test_dawana_dev',)).fetchone()[0]
        can_create = conn.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]
    report['existing_test_database'] = {'exists': existing, 'inspection': 'read-only'}
    if existing:
        with psycopg.connect(**connection, dbname='test_dawana_dev', autocommit=True,
                             options='-c default_transaction_read_only=on') as conn:
            tables = conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE'").fetchone()[0]
            has_history = conn.execute("SELECT to_regclass('public.django_migrations') IS NOT NULL").fetchone()[0]
            history = conn.execute('SELECT count(*) FROM public.django_migrations').fetchone()[0] if has_history else None
            report['existing_test_database'].update(table_count=tables, migration_record_count=history)
    print('Read-only inspection complete. Existing test database will not be reused.', flush=True)
    require(can_create, 'Local database role needs CREATEDB; no permissions were changed')

    name = 'test_dawana_validation_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:10]
    report['new_database'] = name
    # No live credentials or application database are used by Django's test settings.
    os.environ.update(DATABASE_URL='', DB_NAME='postgres', DB_TEST_NAME=name,
                      DB_HOST=str(connection['host']), DB_PORT=str(connection['port']),
                      DB_USER=str(connection['user']), DB_PASSWORD=connection['password'],
                      DJANGO_SETTINGS_MODULE='config.settings.development',
                      DJANGO_SECRET_KEY='synthetic-local-validation-' + uuid.uuid4().hex * 2,
                      DJANGO_DEBUG='True', DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,testserver',
                      PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_synthetic_validation',
                      PAYSTACK_CALLBACK_URL='https://example.test/dic/register/payment-return',
                      DIC_MEMORY_STORAGE='local', DIC_MEMORY_S3_BUCKET='', DIC_MEMORY_S3_ENDPOINT='',
                      DIC_EMAIL_RECOVERY_ENABLED='False', DIC_RECOVERY_DELIVERY_WORKER_ENABLED='False',
                      DIC_SMS_RECOVERY_ADAPTER='', DIC_WHATSAPP_ACCESS_TOKEN='',
                      EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                      AWS_EC2_METADATA_DISABLED='true')
    os.environ.update(AWS_ACCESS_KEY_ID='synthetic-local-only',
                      AWS_SECRET_ACCESS_KEY='synthetic-local-only', AWS_SESSION_TOKEN='',
                      AWS_PROFILE='', DIC_VIDEO_APPROVED_PROVIDERS='youtube,vimeo')
    from cryptography.fernet import Fernet
    os.environ['DIC_RECOVERY_ENCRYPTION_KEY'] = Fernet.generate_key().decode('ascii')
    sys.path.insert(0, str(BACKEND))
    report['phase'] = 'Django checks and migration parity (no application DB connection)'
    import django
    from django.apps import apps
    django.setup()
    from django.conf import settings
    if args.ids_only or args.phase2_and3:
        settings.DIC_ID_PRINT_QA_DIR = ROOT / '.local-preview' / 'id-print-qa' / name
        report['synthetic_print_fixtures'] = str(settings.DIC_ID_PRINT_QA_DIR)
    from django.core.management import call_command
    from django.db import connections
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    require(settings.DATABASES['default']['NAME'] == 'postgres', 'Unexpected default database')
    require(settings.DATABASES['default']['TEST']['NAME'] == name, 'Unexpected test database')
    call_command('check', verbosity=0)
    loader = MigrationLoader(None, ignore_no_migrations=True)
    target = ('dic', '0021_promovideo_campflyer')
    if args.housing_only:
        target = ('dic', '0022_housing_guardians_queue')
    if args.ids_only or args.phase2_and3:
        target = ('dic', '0024_house_badge_colour')
    if args.operations_scoring:
        target = ('dic', '0026_house_score_transaction')
    if args.operations_feedback:
        target = ('dic','0027_feedback_welfare')
    require(target in loader.graph.nodes, f'Migration {target[1]} missing')
    loader.graph.forwards_plan(target)
    changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
    require(not changes, 'Model/migration drift detected; review migration parity before tests')
    report['migration_parity'] = f'PASS: {target[1]} graph and all model states match'

    report['phase'] = 'create uniquely named local validation database'
    with psycopg.connect(**connection, dbname='postgres', autocommit=True) as conn:
        require(not conn.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s)', (name,)).fetchone()[0], 'Generated database already exists; refusing reuse')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    report['database_created'] = True
    print('Created isolated database: ' + name + ' (will be retained, never dropped).', flush=True)

    report['phase'] = 'focused Django tests'
    from django.test.runner import DiscoverRunner
    original_connect = socket.socket.connect
    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('localhost', '127.0.0.1', '::1'):
            raise RuntimeError('External network disabled during local validation')
        return original_connect(sock, address)
    # keepdb preserves the new database on success/failure; no --noinput/drop behavior.
    # This database is unique to this invocation and was created immediately above.
    with tempfile.TemporaryDirectory(prefix='dawana-validation-media-') as media:
        settings.DIC_MEMORY_LOCAL_ROOT = Path(media)
        with patch.object(socket.socket, 'connect', local_connect):
            labels = ['dic.test_allocation', 'dic.test_housing_phase2'] if args.housing_only else LABELS
            if args.ids_only:
                labels = ['dic.test_identity_cards', 'dic.test_id_printing', 'dic.tests.RegistrationApiTests',
                          'dic.test_participant_portal', 'dic.test_participant_remediation', 'dic.test_portal_dashboard',
                          'dic.test_feedback.FeedbackPrivacyTests', 'dic.test_welfare_postponement']
            if args.phase2_and3:
                labels = ['dic.test_allocation', 'dic.test_housing_phase2', 'dic.test_identity_cards', 'dic.test_id_printing']
            if args.operations_scoring:
                labels = ['dic.test_house_configuration', 'dic.test_allocation', 'dic.test_housing_phase2', 'dic.test_scoring']
            if args.operations_feedback:
                labels = ['dic.test_feedback','dic.test_welfare_postponement']
            from django.test.runner import iter_test_cases
            observed, expected = [], []
            def module_name(test_id):
                return '.'.join(test_id.split('.')[:2])
            class RecordingResult(unittest.TextTestResult):
                def startTest(self, test):
                    observed.append(test.id())
                    print(f'RUN {len(observed)}/{len(expected)}: {test.id()}', file=LIVE_OUTPUT, flush=True)
                    super().startTest(test)
                def addSuccess(self, test):
                    super().addSuccess(test)
                    print('PASS: ' + test.id(), file=LIVE_OUTPUT, flush=True)
                def addFailure(self, test, err):
                    super().addFailure(test, err)
                    print('FAIL: ' + test.id() + ' (details in redacted log)', file=LIVE_OUTPUT, flush=True)
                def addError(self, test, err):
                    super().addError(test, err)
                    print('ERROR: ' + test.id() + ' (details in redacted log)', file=LIVE_OUTPUT, flush=True)
            class CountedRunner(DiscoverRunner):
                def build_suite(self, *args, **kwargs):
                    suite = super().build_suite(*args, **kwargs)
                    expected.extend(test.id() for test in iter_test_cases(suite))
                    return suite
                def get_resultclass(self):
                    return RecordingResult
                def suite_result(self, suite, result, **kwargs):
                    missing = sorted(set(expected) - set(observed))
                    skipped = [test.id() for test, reason in result.skipped]
                    strict = args.housing_only or args.ids_only or args.phase2_and3 or args.operations_scoring or args.operations_feedback
                    missing_modules = missing_test_labels(labels, observed, skipped) if strict else []
                    report['test_execution'] = dict(discovered=len(expected), attempted=result.testsRun,
                        executed=result.testsRun - len(skipped),
                        skipped=skipped, missing=missing, missing_modules=missing_modules, stopped=bool(result.shouldStop),
                        by_module={name: {'discovered': sum(module_name(t) == name for t in expected),
                                         'executed': sum(module_name(t) == name and t not in skipped for t in observed)}
                                   for name in sorted(set(module_name(t) for t in expected))})
                    incomplete = bool(not expected or missing or missing_modules or result.testsRun != len(expected) or result.shouldStop)
                    report['test_execution']['complete'] = not (incomplete or (strict and bool(skipped)))
                    report['test_execution']['failures'] = len(result.failures)
                    report['test_execution']['errors'] = len(result.errors)
                    print(f'EXECUTION: {result.testsRun - len(skipped)}/{len(expected)} non-skipped; '
                          f'{len(skipped)} skipped; {len(missing)} missing; stopped={result.shouldStop}.',
                          file=LIVE_OUTPUT, flush=True)
                    return super().suite_result(suite, result, **kwargs) + int(incomplete or (strict and bool(skipped)))
            failures = CountedRunner(verbosity=2, interactive=False, keepdb=True, parallel=1).run_tests(labels)
    connections.close_all()
    report['focused_tests'] = 'PASS' if failures == 0 else f'FAIL: {failures} failing tests/checks'
    if args.housing_only or args.ids_only or args.phase2_and3 or args.operations_scoring or args.operations_feedback:
        report['result'] = 'PASS' if failures == 0 else 'FAIL'
        report['phase'] = 'focused backend validation complete; no media/frontend tests repeated'
        return
    report['phase'] = 'genuine MP4 validation'
    probe = args.ffprobe or shutil.which('ffprobe')
    if probe and Path(probe).is_file():
        report['genuine_mp4'] = genuine_mp4(probe)
    else:
        report['genuine_mp4'] = 'BLOCKED: ffprobe unavailable; mocked MP4 tests are separate'
    report['result'] = 'PASS' if failures == 0 and report['genuine_mp4'].startswith('PASS') else 'FAIL/BLOCKED'
    report['phase'] = 'complete'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffprobe', default='')
    parser.add_argument('--housing-only', action='store_true')
    parser.add_argument('--ids-only', action='store_true')
    parser.add_argument('--phase2-and3', action='store_true')
    parser.add_argument('--operations-scoring', action='store_true', help='Final DIC house configuration, allocation/concurrency and scoring validation in a fresh isolated database')
    parser.add_argument('--operations-feedback', action='store_true', help='Feedback/welfare tests in an approved fresh isolated database; review proposed 0027 privacy/schema first')
    args = parser.parse_args()
    secret_values = []
    report = {'result': 'BLOCKED', 'database_created': False, 'existing_databases_modified': False,
              'database_cleanup': 'none: newly created validation database is deliberately retained'}
    output = io.StringIO()
    LIVE_OUTPUT = sys.stdout
    logdir = ROOT / 'validation-results'
    logdir.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            main(args, report)
    except BaseException as error:
        # Exception text/tracebacks might include configuration: never emit them.
        report['error_class'] = type(error).__name__
        if isinstance(error, ValidationStop):
            report['reason'] = str(error)  # Only fixed messages authored in this runner.
    finally:
        text = output.getvalue()
        for value in sorted(set(secret_values), key=len, reverse=True):
            text = text.replace(value, '[REDACTED]').replace(quote(value, safe=''), '[REDACTED]')
        log = logdir / (run_id + '.txt')
        log.write_text(text, encoding='utf-8')
        summary = logdir / (run_id + '.json')
        summary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(text, end='')
        print(json.dumps(report, indent=2))
        print('Summary: ' + str(summary))
        print('Redacted test log: ' + str(log))
    sys.exit(0 if report['result'] == 'PASS' else 1)
