"""Configuration, tools, safety tests and contained Django mock smoke checks only."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from acceptance_bootstrap.config import AcceptanceConfig, IsolationError
from acceptance_bootstrap.fixtures import fixture_definitions, validate_fixtures
from acceptance_bootstrap.runtime import contained, attach_django


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'FAIL: Invalid bootstrap arguments; values suppressed.\n')


def main(argv=None):
    parser=SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--synthetic-config', action='store_true', help='In-memory test configuration only; no real role approval is asserted.')
    parser.add_argument('--pg-bin')
    args=parser.parse_args(argv)
    results={name:'NOT RUN' for name in ('safety_tests','configuration','toolchain','django_checks','mock_payment','intercepted_email','database_denial')}
    try:
        from test_dic_acceptance_bootstrap import synthetic_env
        env=dict(os.environ)
        if args.synthetic_config:
            env=synthetic_env()
            env['DIC_ACCEPTANCE_DATABASE']='dic_2026_acceptance_'+secrets.token_hex(16)
            env['DIC_ACCEPTANCE_SECRET']=secrets.token_urlsafe(64)
        config=AcceptanceConfig.from_env(env)
        results['configuration']='PASS'
        if args.synthetic_config:
            print('SYNTHETIC CONFIG ONLY: roles, credentials, server identity and name availability are not verified.')
        suite=unittest.defaultTestLoader.loadTestsFromName('test_dic_acceptance_bootstrap.BootstrapTests')
        test_result=unittest.TextTestRunner(verbosity=2).run(suite)
        results['safety_tests']='PASS' if test_result.wasSuccessful() and not test_result.skipped else 'FAIL'
        if results['safety_tests']!='PASS':
            raise IsolationError('Safety tests failed.')
        from dic_backup_readiness import find_tools, versions
        tools=find_tools(bin_dir=args.pg_bin)
        safe_tool_env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP')}
        versions(tools,safe_tool_env)
        results['toolchain']='PASS'
        validate_fixtures(fixture_definitions())
        # This fresh process deliberately supplies only acceptance variables.
        # No .env file is opened. No credential is emitted or persisted.
        django_env={k:v for k,v in env.items() if k.startswith('DIC_ACCEPTANCE_')}
        django_env['DJANGO_SETTINGS_MODULE']='config.settings.acceptance'
        with patch.dict(os.environ,django_env,clear=True), contained(config) as gateway, ExitStack() as stack:
            attach_django(stack)
            import django
            django.setup()
            from django.core.management import call_command
            call_command('check',databases=[],verbosity=0)
            results['django_checks']='PASS'
            from django.db import connection
            try:
                connection.ensure_connection()
            except IsolationError:
                results['database_denial']='PASS'
            else:
                raise IsolationError('Database denial guard inactive.')
            from django.core import mail
            mail.send_mail('Synthetic acceptance message','Synthetic body','acceptance@example.test',['recipient@example.test'])
            if len(mail.outbox)!=1 or mail.outbox[0].to!=['recipient@example.test']:
                raise IsolationError('Email interception failed.')
            results['intercepted_email']='PASS'
            from dic.payments import PaystackClient, verify_webhook_signature
            gateway.select('bootstrap_synthetic','success')
            client=PaystackClient()
            client.initialize_transaction(email='guardian@example.test',amount_kobo=100000,
                reference='bootstrap_synthetic',metadata={'campers':['minor_a','minor_b']})
            if client.verify_transaction('bootstrap_synthetic')['amount']!=100000:
                raise IsolationError('Application payment mock is inactive.')
            body,signature=gateway.webhook('bootstrap_synthetic')
            if not verify_webhook_signature(body,signature,client.secret_key):
                raise IsolationError('Synthetic webhook signing failed.')
            results['mock_payment']='PASS'
    except Exception:
        # Never emit raw exceptions, environment mappings, provider data or URLs.
        print('FAIL: Bootstrap validation stopped; raw diagnostic suppressed. See the last NOT RUN stage.',file=sys.stderr)
        failed=True
    else:
        failed=False
    for name,result in results.items():
        print(result+': '+name)
    print('NOT RUN: PostgreSQL identity/privileges/name availability, provisioning, migrations, fixtures and E2E journeys.')
    print('No database connections/writes, deliveries, backups or cleanup are enabled by this runner.')
    return 1 if failed or any(v!='PASS' for v in results.values()) else 0


if __name__=='__main__':
    sys.exit(main())
