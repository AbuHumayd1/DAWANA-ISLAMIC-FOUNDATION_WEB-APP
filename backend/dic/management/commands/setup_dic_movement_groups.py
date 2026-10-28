"""Configure only the four approved movement groups in local dawana_dev."""
import hashlib
import json
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder


OPS = 'dic.can_view_dic_operations'
IDS = 'dic.can_view_dic_ids'
VIEW = 'dic_movement.can_view_movements'
RECORD = 'dic_movement.can_record_movements'
RELEASE = 'dic_movement.can_authorize_departure'
GROUP_PERMISSIONS = {
    'DIC Movement Viewers': frozenset((OPS, VIEW)),
    'DIC Arrival Officers': frozenset((OPS, 'dic.can_check_in_dic_participants', IDS)),
    'DIC Return Recorders': frozenset((OPS, VIEW, RECORD, IDS)),
    'DIC Release Officers': frozenset((OPS, VIEW, RECORD, IDS, RELEASE)),
}
PERMISSION_MODELS = {
    OPS: 'campedition', IDS: 'campenrollment', 'dic.can_check_in_dic_participants': 'campcheckin',
    VIEW: 'movement', RECORD: 'movement', RELEASE: 'movement',
}


def plan_groups(current, members):
    return [dict(name=name, exists=name in current,
        add=sorted(wanted - current.get(name, set())),
        remove=sorted(current.get(name, set()) - wanted),
        members=sorted(members.get(name, []), key=str))
        for name, wanted in GROUP_PERMISSIONS.items()]


def plan_digest(identity, state, plan):
    payload = json.dumps(dict(identity=identity, state=state, plan=plan), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def auth_snapshot():
    user = get_user_model()
    # Read-only snapshots; never print user security fields or direct grants.
    return dict(
        groups=list(Group.objects.order_by('pk').values_list('pk', 'name')),
        group_permissions=list(Group.permissions.through.objects.order_by('group_id', 'permission_id').values_list('group_id', 'permission_id')),
        memberships=list(user.groups.through.objects.order_by('user_id', 'group_id').values_list('user_id', 'group_id')),
        user_permissions=list(user.user_permissions.through.objects.order_by('user_id', 'permission_id').values_list('user_id', 'permission_id')),
        user_flags=list(user.objects.order_by('pk').values_list('pk', 'is_active', 'is_staff', 'is_superuser')),
        permission_definitions=list(Permission.objects.order_by('pk').values_list('pk', 'content_type_id', 'codename', 'name')),
    )


def verify_after(before, after, target_ids, desired_ids):
    for key in ('memberships', 'user_permissions', 'user_flags', 'permission_definitions'):
        if before[key] != after[key]:
            raise CommandError(f'Authorization state changed unexpectedly ({key}); rolling back this command.')
    approved_names = set(GROUP_PERMISSIONS)
    if {row for row in before['groups'] if row[1] not in approved_names} != {row for row in after['groups'] if row[1] not in approved_names}:
        raise CommandError('Unrelated groups changed; rolling back.')
    if {row for row in before['groups'] if row[1] in approved_names} - set(after['groups']):
        raise CommandError('An existing approved group identity changed; rolling back.')
    if len([row for row in after['groups'] if row[1] in approved_names]) != 4:
        raise CommandError('Expected all four approved groups; rolling back.')
    before_other = {row for row in before['group_permissions'] if row[0] not in target_ids}
    after_other = {row for row in after['group_permissions'] if row[0] not in target_ids}
    if before_other != after_other:
        raise CommandError('Unrelated group grants changed; rolling back.')
    if {row for row in after['group_permissions'] if row[0] in target_ids} != desired_ids:
        raise CommandError('Approved groups do not match the exact grant plan; rolling back.')


class Command(BaseCommand):
    help = 'Preview or apply exactly the approved four movement groups, only in local dawana_dev. Never assigns users.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Apply the previously reviewed matching plan.')
        parser.add_argument('--expected-plan', help='PLAN_SHA256 from a successful dry run; required with --apply.')

    def handle(self, *args, **options):
        config = connection.settings_dict
        if (settings.SETTINGS_MODULE != 'config.settings.development' or connection.vendor != 'postgresql'
                or config.get('NAME') != 'dawana_dev' or config.get('HOST') not in ('localhost', '127.0.0.1', '::1')):
            raise CommandError('Only development settings with local PostgreSQL dawana_dev are allowed; nothing changed.')
        if not admin.site.is_registered(Group):
            raise CommandError('Existing Django Group Admin registration is unavailable; nothing changed.')
        apply = options['apply']
        expected = options.get('expected_plan')
        if apply and (not expected or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected)):
            raise CommandError('--apply requires the exact dry-run --expected-plan hash.')
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                if not apply:
                    cursor.execute('SET TRANSACTION READ ONLY')
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '15s'")
                cursor.execute('SELECT current_database(), host(inet_server_addr()), inet_server_port()')
                identity = cursor.fetchone()
                if identity[0] != 'dawana_dev' or identity[1] not in ('127.0.0.1', '::1') or identity[2] != int(config.get('PORT') or 5432):
                    raise CommandError('Connected database/server identity differs from approved local configuration.')
            self.stdout.write(f'Database: {identity[0]}; PostgreSQL host: {identity[1]}; port: {identity[2]}')
            applied = set(MigrationRecorder(connection).applied_migrations())
            if ('dic_movement', '0001_initial') not in applied or ('dic', '0027_feedback_welfare') in applied:
                raise CommandError('Movement/postponed migration state differs from the confirmed state; no migrations will be run.')
            permissions = {}
            for qualified, model in PERMISSION_MODELS.items():
                app, code = qualified.split('.', 1)
                matches = list(Permission.objects.filter(content_type__app_label=app, codename=code).select_related('content_type'))
                if len(matches) != 1 or matches[0].content_type.model != model:
                    raise CommandError(f'Required permission missing/ambiguous or attached to an unexpected model: {qualified}. Nothing changed; no permissions are fabricated.')
                permissions[qualified] = matches[0]
            before = auth_snapshot()
            names = dict(before['groups'])
            definition_names = {p.pk: qualified for qualified, p in permissions.items()}
            # Include full names for existing extra grants so removals are reviewable.
            for p in Permission.objects.filter(pk__in=[p for g, p in before['group_permissions'] if names[g] in GROUP_PERMISSIONS]).select_related('content_type'):
                definition_names[p.pk] = f'{p.content_type.app_label}.{p.codename}'
            current = {name: set() for name in names.values() if name in GROUP_PERMISSIONS}
            members = {name: [] for name in current}
            for group_id, permission_id in before['group_permissions']:
                if names[group_id] in current:
                    current[names[group_id]].add(definition_names[permission_id])
            for user_id, group_id in before['memberships']:
                if names[group_id] in members:
                    members[names[group_id]].append(user_id)
            plan = plan_groups(current, members)
            fingerprint = plan_digest(identity, before, plan)
            self.stdout.write('Required permission definitions: all six exist on the expected models.')
            for row in plan:
                self.stdout.write(f"{row['name']}: {'existing' if row['exists'] else 'create'}; existing member IDs={row['members']}")
                self.stdout.write('  Add: ' + (', '.join(row['add']) or '(none)'))
                self.stdout.write('  Remove: ' + (', '.join(row['remove']) or '(none)'))
                self.stdout.write('  Exact target: ' + ', '.join(sorted(GROUP_PERMISSIONS[row['name']])))
            self.stdout.write('Existing memberships and direct user grants will not be changed. Group changes affect the effective access of any existing members.')
            self.stdout.write('PLAN_SHA256: ' + fingerprint)
            if not apply:
                self.stdout.write('DRY RUN ONLY: read-only transaction; no group, permission or membership writes.')
                return
            if expected != fingerprint:
                raise CommandError('State changed since preview. Rerun dry run and review; nothing written.')
            # Serialize other instances of this exact setup command. No table/global role locks.
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [2026102604])
            list(Group.objects.select_for_update().filter(name__in=GROUP_PERMISSIONS).order_by('pk'))
            target_ids, desired_ids = set(), set()
            results = []
            for name, desired in GROUP_PERMISSIONS.items():
                group, created = Group.objects.get_or_create(name=name)
                ids = {permissions[qualified].pk for qualified in desired}
                target_ids.add(group.pk)
                desired_ids.update((group.pk, pk) for pk in ids)
                previous = set(group.permissions.values_list('pk', flat=True))
                if previous != ids:
                    group.permissions.set(sorted(ids))
                results.append((name, 'created' if created else 'updated' if previous != ids else 'unchanged'))
            verify_after(before, auth_snapshot(), target_ids, desired_ids)
        for name, status in results:
            self.stdout.write(f'{name}: {status}')
        self.stdout.write('PASS: four exact groups; memberships, user grants/flags, permission definitions and unrelated groups/grants unchanged. Transaction committed.')
