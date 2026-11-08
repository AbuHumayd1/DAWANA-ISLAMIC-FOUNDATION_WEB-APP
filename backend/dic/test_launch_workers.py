from io import StringIO
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from django.core.management import call_command, CommandError
from .management.commands.run_dic_workers import run_cycle


class LaunchWorkerTests(SimpleTestCase):
    @override_settings(DAWANA_WEBSITE_ONLY=True)
    def test_website_mode_cannot_start_application_worker(self):
        with self.assertRaises(CommandError):
            call_command('run_dic_workers', stdout=StringIO())

    @override_settings(DIC_AUTOMATION_ACTOR_ID=7)
    def test_cycle_reuses_housing_and_both_existing_delivery_commands(self):
        with patch('dic.management.commands.run_dic_workers.CampEdition.objects.filter') as rows, \
                patch('dic.management.commands.run_dic_workers.validate_actor'), \
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
                patch('dic.management.commands.run_dic_workers.HEARTBEAT'), \
                patch('dic.management.commands.run_dic_workers.signal.signal'):
            with self.assertRaisesMessage(CommandError, 'Worker configuration is invalid'):
                call_command('run_dic_workers', stdout=StringIO())

    @override_settings(DIC_WORKER_HEARTBEAT_CACHE=True)
    def test_failed_processing_does_not_refresh_shared_readiness(self):
        with patch('dic.management.commands.run_dic_workers.validate_actor'), \
                patch('dic.management.commands.run_dic_workers.call_command', side_effect=RuntimeError('temporary failure')), \
                patch('config.worker_health.beat') as beat:
            with self.assertRaises(RuntimeError):
                run_cycle()
        beat.assert_not_called()
