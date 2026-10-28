"""Database-free Phase 5 graph, model parity and security tests. Never migrates."""
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main(extra_tests=(), phase_label='Phase 5', graph_check=None):
    os.environ.update(DIC_PORTAL_ACCOUNTS_ENABLED='False', DIC_GOOGLE_CLIENT_ID='',
        DIC_GOOGLE_CLIENT_SECRET='', DIC_GOOGLE_REDIRECT_URI='',
        DIC_PORTAL_FRONTEND_URL='', DIC_PORTAL_EMAIL_VERIFY_URL='https://acceptance.example.test/dic/participant')
    spec=importlib.util.spec_from_file_location('phase5_isolation',ROOT/'scripts/validate_dic_finance.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    credentials=helper.configure('test_dic_phase5_policy_unused')
    with ExitStack() as stack:
        helper.guards(stack,credentials,no_database=True)
        from django.apps import apps
        from django.core.management import call_command
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.state import ProjectState
        from django.test import SimpleTestCase, override_settings
        from django.test.runner import iter_test_cases
        # Synthetic policy fixtures repeatedly set/check passwords. Keep Django's
        # hashing API and every rejection assertion, but avoid production PBKDF2
        # work in this process only. override_settings restores settings/caches.
        stack.enter_context(override_settings(
            PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']))
        call_command('check',verbosity=1)
        loader=MigrationLoader(None)
        target=('dic','0031_phase5_feedback_welfare')
        plan=loader.graph.forwards_plan(target)
        expected=['0026_house_score_transaction','0028_registration_privacy_measurements',
            '0029_authorized_tutor_registration','0030_portal_account_authentication','0027_feedback_welfare',target[1]]
        if loader.detect_conflicts() or [name for app,name in plan if app=='dic' and name in expected] != expected:
            raise RuntimeError('Unexpected Phase 5 migration ordering.')
        actual=ProjectState.from_apps(apps);prepared=loader.project_state(target)
        for name in ('anonymouscamperresponse','camperfeedbackreceipt','identifiedfeedback',
                'lecturerfeedbackaccess','welfarereport','welfareevent'):
            if actual.models['dic',name] != prepared.models['dic',name]:
                raise RuntimeError('Phase 5 model/migration mismatch: '+name)
        if graph_check is not None:
            graph_check(loader,actual)
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'dic.test_feedback.FeedbackPrivacyTests','dic.test_welfare_postponement.WelfarePostponementTests',
            'dic.test_phase5_policy.Phase5PolicyTests',
            'dic.test_portal_phase3.PortalPhase3PolicyTests','dic.test_portal_accounts.PortalAccountPolicyTests',
            'dic.test_portal_eligibility.PortalEligibilityPolicyTests',
            'dic.test_registration_accounts.RegistrationAccountPolicyTests']+list(extra_tests))
        cases=list(iter_test_cases(suite))
        if not cases or any(not isinstance(case,SimpleTestCase) or case.databases for case in cases):
            raise RuntimeError('Database-writing tests are forbidden.')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful() or result.skipped:
            raise RuntimeError('Phase 5 policy validation failed or incomplete.')
        print(f'PASS: {phase_label}: {result.testsRun} database-free policy tests, graph and model parity (test-only hasher).')


if __name__=='__main__':
    main()
