"""No Django, database, processes or network needed for startup failure tests."""
from contextlib import redirect_stderr
from io import StringIO
from unittest import TestCase
from unittest.mock import patch
import entrypoint
from startup_errors import StartupError


class StartupDiagnosticsTests(TestCase):
    def test_unexpected_exception_is_replaced_with_the_actionable_stage_only(self):
        def failure():
            raise RuntimeError('postgresql://user:private@internal-private/secret')
        with self.assertRaises(StartupError) as error:
            entrypoint.stage('DJ_SETUP', 'Review production settings.', failure)
        self.assertEqual(str(error.exception), 'DJ_SETUP: Review production settings.')

    def test_main_logs_known_code_and_remedy_without_environment_values(self):
        output = StringIO()
        with patch.object(entrypoint, 'configure', side_effect=StartupError('CFG_CONFLICT_DB_SSLMODE',
                'Remove the conflicting DB_SSLMODE override.')), redirect_stderr(output):
            self.assertEqual(entrypoint.main(), 1)
        self.assertIn('[CFG_CONFLICT_DB_SSLMODE]', output.getvalue())
        self.assertIn('Remove the conflicting DB_SSLMODE override.', output.getvalue())

    def test_main_redacts_unexpected_configuration_exception(self):
        output = StringIO()
        with patch.object(entrypoint, 'configure', side_effect=RuntimeError('private-key internal-address')), \
                redirect_stderr(output):
            self.assertEqual(entrypoint.main(), 1)
        self.assertIn('[CFG_NORMALIZE]', output.getvalue())
        self.assertNotIn('private-key', output.getvalue())
        self.assertNotIn('internal-address', output.getvalue())
