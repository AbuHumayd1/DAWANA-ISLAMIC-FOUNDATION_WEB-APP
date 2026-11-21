"""Safe, database-free checks for the fail-closed 0048 Render release runner."""
from unittest import TestCase
from unittest.mock import patch, MagicMock
import os

from config import studio_0048_migration as release


class CarouselMigrationReleaseTests(TestCase):
    def test_backup_digest_must_match_reviewed_archive(self):
        env = {
            'RENDER': 'true', 'RENDER_GIT_COMMIT': 'a' * 40,
            'DAWANA_0048_APPROVAL': release.APPROVAL,
            'DAWANA_0048_FRESH_BACKUP_SHA256': 'a' * 64,
            'DAWANA_0048_ARCHIVE_READABLE': 'yes',
        }
        config = {'NAME': release.EXPECTED_DATABASE,
                  'USER': release.EXPECTED_ROLE, 'PORT': '5432', 'HOST': 'db.example.test'}
        self.assertEqual(len(release.APPROVED_FRESH_BACKUP_SHA256), 64)
        with self.assertRaisesRegex(release.Stop, 'BACKUP_DIGEST_MISMATCH'):
            release.validate_approval(env, 'config.settings.render', config)
        env['DAWANA_0048_FRESH_BACKUP_SHA256'] = release.APPROVED_FRESH_BACKUP_SHA256
        env['DAWANA_0048_ARCHIVE_READABLE'] = 'no'
        with self.assertRaisesRegex(release.Stop, 'BACKUP_NOT_VERIFIED_READABLE'):
            release.validate_approval(env, 'config.settings.render', config)
        env['DAWANA_0048_ARCHIVE_READABLE'] = 'yes'
        self.assertEqual(release.validate_approval(
            env, 'config.settings.render', config)['database'], release.EXPECTED_DATABASE)

    def test_wrong_approval_and_release_context_are_rejected(self):
        config = {'NAME': release.EXPECTED_DATABASE,
                  'USER': release.EXPECTED_ROLE, 'PORT': '5432', 'HOST': 'db.example.test'}
        with self.assertRaisesRegex(release.Stop, 'RENDER_REQUIRED'):
            release.validate_approval({}, 'config.settings.render', config)
        env = {'RENDER': 'true', 'RENDER_GIT_COMMIT': 'a' * 40,
               'DAWANA_0048_APPROVAL': 'unapproved'}
        with self.assertRaisesRegex(release.Stop, 'OWNER_APPROVAL_REQUIRED'):
            release.validate_approval(env, 'config.settings.render', config)

    def test_exact_migration_sha_and_operation_count(self):
        from importlib import import_module
        migration = import_module('dic.migrations.0048_studio_carousels').Migration('0048_studio_carousels', 'dic')
        release.verify_migration(migration)
        migration.operations = migration.operations[:-1]
        with self.assertRaisesRegex(release.Stop, 'MIGRATION_OPERATIONS_CHANGED'):
            release.verify_migration(migration)

    def test_unrelated_plan_refused_without_any_schema_change(self):
        # Ensure the runner has an explicit single-migration guard, not a blanket migrate.
        import inspect
        src = inspect.getsource(release.apply_exact_0048)
        self.assertIn('len(plan) == 1', src)
        self.assertIn('UNEXPECTED_PENDING_MIGRATION_PLAN', src)
        self.assertIn('verify_tables(cursor, False)', src)
        self.assertIn('verify_tables(cursor, True)', src)
        self.assertIn('transaction.atomic', src)

    def test_runner_is_non_promoting_only_via_build_wrapper(self):
        from pathlib import Path
        backend = Path(__file__).resolve().parents[1]
        build = (backend / 'native-build.sh').read_text()
        wrapper = (backend / 'media-0048-migration-apply-build.sh').read_text()
        self.assertIn('DAWANA_0048_APPROVAL', build)
        self.assertIn('media-0048-migration-apply-build.sh', build)
        self.assertIn('exit 1', wrapper)
        self.assertNotIn('manage.py migrate', wrapper)
