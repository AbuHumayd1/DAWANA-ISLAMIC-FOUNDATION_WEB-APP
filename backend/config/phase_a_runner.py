"""Real migrations followed by a flush of disposable test-only reference seeds."""
from django.core.management import call_command
from django.test.runner import DiscoverRunner


class PhaseARunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        old = super().setup_databases(**kwargs)
        from django.db import connection
        if connection.settings_dict['NAME'] not in ('test_dic_core_20261112190000_50484153', 'test_dic_tutor_20261112190000_50484153'):
            raise RuntimeError('Only the dedicated disposable Phase A test database can be flushed.')
        call_command('flush', verbosity=0, interactive=False)
        return old

    def get_test_runner_kwargs(self):
        import unittest
        class ClearCacheResult(unittest.TextTestResult):
            def startTest(self, test):
                from django.core.cache import cache
                cache.clear()
                super().startTest(test)
        return {**super().get_test_runner_kwargs(), 'resultclass': ClearCacheResult}
