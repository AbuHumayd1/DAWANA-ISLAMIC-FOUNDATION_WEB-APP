"""GitHub-hosted disposable PostgreSQL acceptance; never a local/prod launcher."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sanitize_libpq_environment():
    # Empty service settings still reach libpq; remove inherited overrides.
    for name in ('PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE', 'PGHOST', 'PGHOSTADDR',
                 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD'):
        os.environ.pop(name, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partition', choices=('core', 'tutor', 'movement', 'assistance'))
    parser.add_argument('--summarize', action='store_true')
    parser.add_argument('--syntax-check', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('DAWANA_CI_ACCEPTANCE') != '1':
        parser.error('Only the ephemeral GitHub Actions acceptance job is supported.')
    if args.syntax_check:
        checked = []
        for directory, subdirectories, files in os.walk(ROOT / 'backend'):
            subdirectories[:] = [name for name in subdirectories
                                 if name not in ('.venv', 'venv', '__pycache__', '.runtime')]
            checked.extend(Path(directory) / name for name in files if name.endswith('.py'))
        checked.extend(ROOT / 'scripts' / name for name in ('run_backend_ci.py', 'test_production_policies.py'))
        for path in checked:
            compile(path.read_bytes(), str(path), 'exec')  # Parse only; no imports, execution or pyc files.
        print('PASS: Python syntax compiled for ' + str(len(checked)) + ' source files; no tests executed.')
        return 0
    if args.summarize:
        reports = list((Path(os.environ['RUNNER_TEMP']) / 'dawana-backend-results').glob('*.json'))
        expected = os.environ.get('DAWANA_CI_REPORT', '')
        if expected not in ('policy', 'core', 'tutor', 'movement', 'assistance'):
            parser.error('An exact job report identity is required.')
        if len(reports) != 1 or reports[0].stem != expected:
            print('NOT VERIFIED: the exact expected job report is missing or ambiguous.')
            return 1
        test_step = os.environ.get('DAWANA_CI_TEST_STEP', '')
        successful = test_step == 'success'
        for path in reports:
            report = json.loads(path.read_text(encoding='utf-8'))
            summary = {key: value for key, value in report.items()
                       if not key.endswith('_ids') and key != 'skipped_tests'}
            if test_step != 'success':
                summary['status'] = 'not_verified'
            summary['test_step_outcome'] = test_step or 'missing'
            print(path.stem + ': ' + json.dumps(summary, sort_keys=True))
            complete = (isinstance(report.get('discovered'), int) and report['discovered'] > 0
                and report.get('started') == report['discovered'] == report.get('passed')
                and all(report.get(key) == 0 for key in ('failures', 'errors', 'skipped',
                    'expected_failures', 'unexpected_successes', 'not_started')))
            successful = successful and report.get('status') == 'passed' and complete
        return int(not successful)
    if not args.partition:
        parser.error('--partition is required unless summarizing.')
    existing_report = Path(os.environ['RUNNER_TEMP']) / 'dawana-backend-results' / (args.partition + '.json')
    if existing_report.exists():
        parser.error('Existing result evidence cannot be reused or overwritten; use a fresh CI job.')
    # Refuse rather than reading an accidentally included dotenv file.
    if any(path.exists() or path.is_symlink() for path in (ROOT / '.env', ROOT / 'backend/.env')):
        parser.error('CI checkout must not contain dotenv files.')
    name = 'test_dic_' + args.partition + '_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:8]
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.ci', DAWANA_CI_DATABASE=name,
        AWS_EC2_METADATA_DISABLED='true', DATABASE_URL='')
    sanitize_libpq_environment()
    sys.path.insert(0, str(ROOT / 'backend'))
    from config.ci_acceptance import AcceptanceRunner, guarded_connections, write_report
    try:
        with guarded_connections(name, os.environ['DAWANA_CI_PG_PORT']):
            import django
            django.setup()
            from django.apps import apps
            from django.db.migrations.loader import MigrationLoader
            from django.db.migrations.autodetector import MigrationAutodetector
            from django.db.migrations.state import ProjectState
            loader = MigrationLoader(None, ignore_no_migrations=True)
            if loader.detect_conflicts():
                raise RuntimeError('Migration graph conflicts; CI will not rewrite migrations.')
            if ('dic', '0036_private_participant_storage') not in loader.graph.nodes:
                raise RuntimeError('Required production migration 0036 is absent from the checkout.')
            plan = loader.graph.forwards_plan(('dic', '0036_private_participant_storage'))
            required_order = [
                '0026_house_score_transaction', '0028_registration_privacy_measurements',
                '0029_authorized_tutor_registration', '0030_portal_account_authentication',
                '0027_feedback_welfare', '0031_phase5_feedback_welfare', '0032_phase4_timetables',
                '0033_launch_completion', '0034_approved_2026_fees',
                '0035_production_payment_mode_and_official_details', '0036_private_participant_storage',
            ]
            positions = [plan.index(('dic', name)) for name in required_order]
            if positions != sorted(positions):
                raise RuntimeError('Required migration dependency/run_before ordering is not preserved.')
            if MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph):
                raise RuntimeError('Model/migration drift; CI will not generate migrations.')
            return AcceptanceRunner(args.partition).run_tests([])
    except BaseException as error:
        report = Path(os.environ['RUNNER_TEMP']) / 'dawana-backend-results' / (args.partition + '.json')
        if not report.exists():
            write_report(args.partition, {'status': 'setup_or_runner_failed', 'started': 0,
                'passed': 0, 'exception_type': type(error).__name__})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
