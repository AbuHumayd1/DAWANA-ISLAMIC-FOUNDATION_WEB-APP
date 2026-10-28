"""Database-free Phase 3 checks only. No provisioning or migration action exists."""
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import os
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Independent of developer OAuth settings; tests opt in explicitly.
    os.environ.update(DIC_PORTAL_ACCOUNTS_ENABLED='False', DIC_GOOGLE_CLIENT_ID='',
        DIC_GOOGLE_CLIENT_SECRET='', DIC_GOOGLE_REDIRECT_URI='', DIC_PORTAL_FRONTEND_URL='',
        DIC_PORTAL_EMAIL_VERIFY_URL='https://acceptance.example.test/dic/participant')
    spec = importlib.util.spec_from_file_location('phase3_isolation', ROOT / 'scripts/validate_dic_finance.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    credentials = helper.configure('test_dic_phase3_policy_unused')
    with ExitStack() as stack:
        helper.guards(stack, credentials, no_database=True)
        from django.core.management import call_command
        from django.db.migrations.loader import MigrationLoader
        from django.test import SimpleTestCase
        from django.test.runner import iter_test_cases
        call_command('check', verbosity=1)
        loader = MigrationLoader(None)
        target = ('dic', '0030_portal_account_authentication')
        plan = loader.graph.forwards_plan(target)
        if loader.detect_conflicts() or ('dic', '0027_feedback_welfare') in plan or ('dic', '0029_authorized_tutor_registration') not in plan:
            raise RuntimeError('Unexpected Phase 3 migration graph.')
        from django.apps import apps
        from django.db.migrations.state import ProjectState
        actual = ProjectState.from_apps(apps)
        prepared = loader.project_state(target)
        for name in ('portalaccount', 'portalaccountbooking', 'portalaccountsession', 'portalgooglelink', 'portaloauthattempt'):
            if actual.models['dic', name] != prepared.models['dic', name]:
                raise RuntimeError('Account model/migration state mismatch: ' + name)
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'dic.test_portal_phase3.PortalPhase3PolicyTests', 'dic.test_portal_accounts.PortalAccountPolicyTests',
            'dic.test_portal_eligibility.PortalEligibilityPolicyTests',
            'dic.test_registration_accounts.RegistrationAccountPolicyTests'])
        cases = list(iter_test_cases(suite))
        if len(cases) != 74 or any(not isinstance(case, SimpleTestCase) or case.databases for case in cases):
            raise RuntimeError('Unexpected policy test manifest.')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful() or result.skipped or result.testsRun != 74:
            raise RuntimeError('Phase 3 policy checks failed or incomplete.')


if __name__ == '__main__':
    main()
