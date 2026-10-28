"""Database-free contract and permission-boundary checks for approved staff groups."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import PermissionDenied
from dic.management.commands.setup_dic_movement_groups import Command, GROUP_PERMISSIONS, plan_groups, plan_digest, verify_after
from .services import require, departure_authority


class MovementGroupSetupTests(SimpleTestCase):
    @override_settings(SETTINGS_MODULE='config.settings.development')
    def test_command_refuses_other_databases_or_remote_hosts_before_connecting(self):
        for name, host in [('test_dic_portal_2026_local', '127.0.0.1'), ('other', 'localhost'), ('dawana_dev', 'remote.example.test')]:
            fake = MagicMock(vendor='postgresql', settings_dict={'NAME': name, 'HOST': host})
            with patch('dic.management.commands.setup_dic_movement_groups.connection', fake), self.assertRaises(CommandError):
                Command().handle(apply=False, expected_plan=None)
            fake.cursor.assert_not_called()

    def test_four_exact_role_contracts(self):
        expected = {
            'DIC Movement Viewers': {'dic.can_view_dic_operations', 'dic_movement.can_view_movements'},
            'DIC Arrival Officers': {'dic.can_view_dic_operations', 'dic.can_check_in_dic_participants', 'dic.can_view_dic_ids'},
            'DIC Return Recorders': {'dic.can_view_dic_operations', 'dic_movement.can_view_movements', 'dic_movement.can_record_movements', 'dic.can_view_dic_ids'},
            'DIC Release Officers': {'dic.can_view_dic_operations', 'dic_movement.can_view_movements', 'dic_movement.can_record_movements', 'dic.can_view_dic_ids', 'dic_movement.can_authorize_departure'},
        }
        self.assertEqual(GROUP_PERMISSIONS, expected)

    def test_planning_existing_exact_groups_is_idempotent(self):
        current = {name: set(perms) for name, perms in GROUP_PERMISSIONS.items()}
        members = {'DIC Arrival Officers': [3, 1]}
        before = deepcopy((current, members))
        plan = plan_groups(current, members)
        self.assertTrue(all(row['exists'] and not row['add'] and not row['remove'] for row in plan))
        self.assertEqual((current, members), before)
        self.assertEqual(next(row for row in plan if row['name'] == 'DIC Arrival Officers')['members'], [1, 3])

    def test_plan_removes_extras_only_from_named_groups_and_preserves_member_list(self):
        current = {'DIC Movement Viewers': {'dic.can_view_dic_finance'}, 'Unrelated': {'auth.change_user'}}
        plan = plan_groups(current, {'DIC Movement Viewers': [7]})
        self.assertEqual(len(plan), 4)
        viewer = next(row for row in plan if row['name'] == 'DIC Movement Viewers')
        self.assertEqual(viewer['remove'], ['dic.can_view_dic_finance'])
        self.assertEqual(viewer['members'], [7])
        self.assertEqual(current['Unrelated'], {'auth.change_user'})

    def test_plan_hash_detects_membership_or_grant_changes(self):
        plan = plan_groups({}, {})
        first = plan_digest(('dawana_dev', '127.0.0.1', 5432), {'memberships': []}, plan)
        self.assertEqual(first, plan_digest(('dawana_dev', '127.0.0.1', 5432), {'memberships': []}, plan))
        self.assertNotEqual(first, plan_digest(('dawana_dev', '127.0.0.1', 5432), {'memberships': [(1, 2)]}, plan))

    def state(self):
        return dict(groups=[(1, 'Unrelated')], group_permissions=[(1, 99)], memberships=[(7, 1)],
            user_permissions=[(7, 88)], user_flags=[(7, True, True, False)], permission_definitions=[(99, 1, 'view', 'View')])

    def configured_state(self, before):
        state = deepcopy(before)
        state['groups'] += [(pk, name) for pk, name in enumerate(GROUP_PERMISSIONS, 2)]
        state['group_permissions'] += [(pk, 100 + pk) for pk in range(2, 6)]
        return state

    def test_postcheck_accepts_only_scoped_group_changes(self):
        before = self.state(); after = self.configured_state(before)
        verify_after(before, after, set(range(2, 6)), {(pk, 100 + pk) for pk in range(2, 6)})
        verify_after(after, deepcopy(after), set(range(2, 6)), {(pk, 100 + pk) for pk in range(2, 6)})

    def test_postcheck_rejects_membership_user_definition_or_unrelated_group_changes(self):
        before = self.state()
        for key in ['memberships', 'user_permissions', 'user_flags', 'permission_definitions', 'groups', 'group_permissions']:
            after = self.configured_state(before)
            after[key] = after[key][1:]
            with self.subTest(key=key), self.assertRaises(CommandError):
                verify_after(before, after, set(range(2, 6)), {(pk, 100 + pk) for pk in range(2, 6)})

    def test_only_release_group_authorizes_departure_for_non_superusers(self):
        for name, permissions in GROUP_PERMISSIONS.items():
            actor = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False,
                has_perm=lambda permission, allowed=permissions: permission in allowed)
            data = dict(authorization_checked=True, authorization_reference='Synthetic evidence reference')
            if name == 'DIC Release Officers':
                self.assertEqual(departure_authority(actor, data), data['authorization_reference'])
            else:
                with self.assertRaises(PermissionDenied): departure_authority(actor, data)

    def test_non_superuser_without_movement_grant_is_denied(self):
        actor = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, is_superuser=False,
            has_perm=lambda permission: permission == 'dic.can_view_dic_operations')
        for permission in ['dic_movement.can_view_movements', 'dic_movement.can_record_movements', 'dic_movement.can_authorize_departure']:
            with self.subTest(permission=permission), self.assertRaises(PermissionDenied): require(actor, permission)

    def test_groups_use_existing_django_admin_registration(self):
        self.assertTrue(admin.site.is_registered(Group))
