"""Run only database-free group policy checks with external/DB connections denied."""
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import unittest


def main():
    path = Path(__file__).resolve().with_name('validate_dic_finance.py')
    spec = importlib.util.spec_from_file_location('movement_group_policy_isolation', path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    # This name is only configuration: no database is created or connected to.
    credentials = helper.configure('test_dic_movement_groups_unused')
    with ExitStack() as stack:
        helper.guards(stack, credentials, no_database=True)
        from django.test import SimpleTestCase
        from django.test.runner import iter_test_cases
        from django.test.utils import setup_test_environment, teardown_test_environment
        label = 'dic_movement.test_groups.MovementGroupSetupTests'
        suite = unittest.defaultTestLoader.loadTestsFromName(label)
        cases = list(iter_test_cases(suite))
        if len(cases) != 10 or not all(isinstance(case, SimpleTestCase) and not case.databases for case in cases):
            raise RuntimeError('Unexpected test manifest or database-enabled test; stop.')
        setup_test_environment()
        try: result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally: teardown_test_environment()
        if result.testsRun != 10 or not result.wasSuccessful() or result.skipped:
            raise RuntimeError('Focused group validation failed, skipped or incomplete.')
        print('PASS: 10 database-free group tests; no database connections or writes.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        sys.exit(1)
