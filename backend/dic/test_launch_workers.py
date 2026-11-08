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
                patch('dic.management.commands.run_dic_workers.call_command') as commands, \
                patch('dic.management.commands.run_dic_workers.HEARTBEAT') as heartbeat:
            rows.return_value.values_list.return_value = [5]
            run_cycle()
        self.assertEqual([call.args[0] for call in commands.call_args_list],
            ['send_dic_recovery_messages', 'send_dic_portal_messages', 'process_dic_followups'])
        self.assertEqual(commands.call_args_list[2].kwargs['actor'], 7)
        heartbeat.touch.assert_called_once()
