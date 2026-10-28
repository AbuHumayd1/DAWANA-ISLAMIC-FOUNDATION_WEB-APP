"""Run only the stateless assisted-preparation tests, with DB/network access blocked."""
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import unittest


def main():
    path = Path(__file__).resolve().with_name('validate_dic_finance.py')
    spec = importlib.util.spec_from_file_location('assisted_preparation_isolation', path)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    credentials = helper.configure('test_dic_assisted_preparation_unused')
    with ExitStack() as stack:
        helper.guards(stack, credentials, no_database=True)
        from django.test import SimpleTestCase
        from django.test.runner import iter_test_cases
        from django.test.utils import setup_test_environment, teardown_test_environment
        suite = unittest.defaultTestLoader.loadTestsFromName('dic.test_assisted_preparation.AssistedPreparationTests')
        cases = list(iter_test_cases(suite))
        if len(cases) != 10 or not all(isinstance(case, SimpleTestCase) and not case.databases for case in cases):
            raise RuntimeError('Unexpected assisted-preparation test manifest or database requirement.')
        setup_test_environment()
        try: result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally: teardown_test_environment()
        if not result.wasSuccessful() or result.testsRun != 10 or result.skipped:
            raise RuntimeError('Assisted preparation checks failed, skipped or incomplete.')
        print('PASS: 10 database-free preparation tests; no records or payments created.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STOP:', type(error).__name__, file=sys.stderr)
        if isinstance(error, RuntimeError): print(str(error), file=sys.stderr)
        sys.exit(1)
