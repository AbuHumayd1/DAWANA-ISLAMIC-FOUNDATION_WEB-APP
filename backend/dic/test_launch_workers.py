from io import StringIO
from unittest.mock import patch
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.core.management import call_command, CommandError
from .management.commands.run_dic_workers import run_cycle


class LaunchWorkerTests(SimpleTestCase):
    @override_settings(DAWANA_WEBSITE_ONLY=False, DIC_BACKGROUND_WORKER_ENABLED=True, DIC_AUTOMATION_ACTOR_ID=0)
    def test_absent_actor_setting_refuses_worker_without_lookup(self):
        from .management.commands.run_dic_workers import validate_actor
        del settings.DIC_AUTOMATION_ACTOR_ID
        with patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                patch('dic.management.commands.run_dic_workers.validate_worker_configuration') as configuration, \
                patch('dic.management.commands.run_dic_workers.run_cycle') as cycle:
            with self.assertRaisesMessage(CommandError, 'automation actor'):
                call_command('run_dic_workers', stdout=StringIO())
            with self.assertRaisesMessage(CommandError, 'automation actor'):
                validate_actor()
        users.assert_not_called()
        configuration.assert_not_called()
        cycle.assert_not_called()

    @override_settings(DAWANA_WEBSITE_ONLY=False, DIC_BACKGROUND_WORKER_ENABLED=True, DIC_AUTOMATION_ACTOR_ID=0)
    def test_missing_actor_refuses_worker_before_lookup_or_job_processing(self):
        with patch('dic.management.commands.run_dic_workers.validate_worker_configuration') as configuration, \
                patch('dic.management.commands.run_dic_workers.validate_actor') as actor, \
                patch('dic.management.commands.run_dic_workers.run_cycle') as cycle:
            with self.assertRaisesMessage(CommandError, 'automation actor'):
                call_command('run_dic_workers', stdout=StringIO())
        configuration.assert_not_called()
        actor.assert_not_called()
        cycle.assert_not_called()

    @override_settings(DAWANA_WEBSITE_ONLY=True)
    def test_website_mode_cannot_start_application_worker(self):
        with self.assertRaises(CommandError):
            call_command('run_dic_workers', stdout=StringIO())

    @override_settings(DAWANA_WEBSITE_ONLY=False, DIC_BACKGROUND_WORKER_ENABLED=True)
    def test_invalid_actor_configuration_prevents_lookup_and_processing(self):
        for value in (None, 0, -1, '', 'invalid', '7', True, 7.5, 2**63):
            with self.subTest(value=value), self.settings(DIC_AUTOMATION_ACTOR_ID=value), \
                    patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                    patch('dic.management.commands.run_dic_workers.validate_worker_configuration') as configuration, \
                    patch('dic.management.commands.run_dic_workers.call_command') as jobs:
                with self.assertRaisesMessage(CommandError, 'automation actor'):
                    call_command('run_dic_workers', stdout=StringIO())
                configuration.assert_not_called()
                with self.assertRaisesMessage(CommandError, 'automation actor'):
                    run_cycle()
                users.assert_not_called()
                jobs.assert_not_called()

    @override_settings(DIC_AUTOMATION_ACTOR_ID=7)
    def test_cycle_reuses_housing_and_both_existing_delivery_commands(self):
        with patch('dic.management.commands.run_dic_workers.CampEdition.objects.filter') as rows, \
                patch('dic.management.commands.run_dic_workers.validate_worker_configuration'), \
                patch('dic.management.commands.run_dic_workers.validate_actor', return_value=7), \
                patch('dic.management.commands.run_dic_workers.call_command') as commands, \
                patch('dic.management.commands.run_dic_workers.HEARTBEAT') as heartbeat:
            rows.return_value.values_list.return_value = [5]
            run_cycle()
        self.assertEqual([call.args[0] for call in commands.call_args_list],
            ['send_dic_recovery_messages', 'send_dic_portal_messages', 'process_dic_followups'])
        self.assertEqual(commands.call_args_list[2].kwargs['actor'], 7)
        heartbeat.touch.assert_called_once()

    @override_settings(DAWANA_WEBSITE_ONLY=False, DIC_BACKGROUND_WORKER_ENABLED=True, DIC_AUTOMATION_ACTOR_ID=7)
    def test_configuration_failure_exits_instead_of_silently_retrying(self):
        with patch('dic.management.commands.run_dic_workers.run_cycle', side_effect=CommandError('invalid actor')), \
                patch('dic.management.commands.run_dic_workers.validate_worker_configuration'), \
                patch('dic.management.commands.run_dic_workers.HEARTBEAT'), \
                patch('dic.management.commands.run_dic_workers.signal.signal'):
            with self.assertRaisesMessage(CommandError, 'Worker configuration is invalid'):
                call_command('run_dic_workers', stdout=StringIO())

    @override_settings(DIC_WORKER_HEARTBEAT_CACHE=True)
    def test_failed_processing_does_not_refresh_shared_readiness(self):
        with patch('dic.management.commands.run_dic_workers.validate_actor'), \
                patch('dic.management.commands.run_dic_workers.validate_worker_configuration'), \
                patch('dic.management.commands.run_dic_workers.call_command', side_effect=RuntimeError('temporary failure')), \
                patch('config.worker_health.beat') as beat:
            with self.assertRaises(RuntimeError):
                run_cycle()
        beat.assert_not_called()

    @override_settings(DIC_RECOVERY_ENCRYPTION_KEY='')
    def test_missing_key_prevents_any_actor_lookup_or_job_processing(self):
        with patch('dic.management.commands.run_dic_workers.validate_actor') as actor, \
                patch('dic.management.commands.run_dic_workers.call_command') as jobs:
            with self.assertRaisesMessage(CommandError, 'DIC_RECOVERY_ENCRYPTION_KEY'):
                run_cycle()
        actor.assert_not_called()
        jobs.assert_not_called()

    def test_invalid_keys_prevent_lookup_and_job_processing(self):
        for key in (None, 'not-a-fernet-key', 123):
            with self.subTest(key=key), self.settings(DIC_RECOVERY_ENCRYPTION_KEY=key), \
                    patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                    patch('dic.management.commands.run_dic_workers.call_command') as jobs:
                with self.assertRaisesMessage(CommandError, 'DIC_RECOVERY_ENCRYPTION_KEY'):
                    run_cycle()
                users.assert_not_called()
                jobs.assert_not_called()

    @override_settings(DIC_RECOVERY_ENCRYPTION_KEY='')
    def test_absent_key_prevents_lookup_and_job_processing(self):
        del settings.DIC_RECOVERY_ENCRYPTION_KEY
        with patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                patch('dic.management.commands.run_dic_workers.call_command') as jobs:
            with self.assertRaisesMessage(CommandError, 'DIC_RECOVERY_ENCRYPTION_KEY'):
                run_cycle()
        users.assert_not_called()
        jobs.assert_not_called()

    def test_missing_email_configuration_prevents_job_claims(self):
        with patch('dic.recovery.recovery_encryption_configured', return_value=True), \
                patch('dic.recovery.channel_available', return_value=False), \
                patch('dic.management.commands.run_dic_workers.validate_actor') as actor, \
                patch('dic.management.commands.run_dic_workers.call_command') as jobs:
            with self.assertRaisesMessage(CommandError, 'email backend'):
                run_cycle()
        actor.assert_not_called()
        jobs.assert_not_called()

    def test_invalid_verification_url_prevents_lookup_and_job_claims(self):
        from django.core.exceptions import ValidationError
        with patch('dic.recovery.recovery_encryption_configured', return_value=True), \
                patch('dic.recovery.channel_available', return_value=True), \
                patch('dic.registration_accounts.verification_url', side_effect=ValidationError('Invalid URL')), \
                patch('dic.management.commands.run_dic_workers.validate_actor') as actor, \
                patch('dic.management.commands.run_dic_workers.call_command') as jobs:
            with self.assertRaisesMessage(CommandError, 'verification URL'):
                run_cycle()
        actor.assert_not_called()
        jobs.assert_not_called()

    @override_settings(DIC_AUTOMATION_ACTOR_ID=7)
    def test_worker_checks_all_permissions_before_processing(self):
        from .management.commands.run_dic_workers import validate_actor
        with patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                patch('dic.housing_service.permitted') as permitted:
            validate_actor()
            self.assertEqual([call.args[1] for call in permitted.call_args_list],
                ['can_process_housing_queue', 'can_allocate_participants', 'can_approve_housing_guardians'])

    @override_settings(DIC_AUTOMATION_ACTOR_ID=7)
    def test_unauthorized_actor_cannot_process_jobs(self):
        from django.core.exceptions import PermissionDenied
        with patch('dic.management.commands.run_dic_workers.validate_worker_configuration'), \
                patch('dic.management.commands.run_dic_workers.get_user_model') as users, \
                patch('dic.housing_service.permitted', side_effect=PermissionDenied()), \
                patch('dic.management.commands.run_dic_workers.call_command') as jobs:
            users.return_value.DoesNotExist = LookupError
            with self.assertRaisesMessage(CommandError, 'lacks required permissions'):
                run_cycle()
        jobs.assert_not_called()
