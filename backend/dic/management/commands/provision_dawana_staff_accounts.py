"""Owner-reviewed initial staff identities; no passwords, invitations or automatic access."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from dic.models import DICAdminAuditEvent
from dic.staff_roles import ROLES

OPERATIONS_GROUP = 'DIC Operations Administrators'
MEDIA_GROUP = 'DAWANA Media Studio Personnel'
ACCOUNTS = (
    ('Operations_1', '', OPERATIONS_GROUP),
    ('Operations_2', '', OPERATIONS_GROUP),
    ('Operations_3', '', OPERATIONS_GROUP),
    ('Operations_4', '', OPERATIONS_GROUP),
    ('Operations_5', '', OPERATIONS_GROUP),
    ('Dawana_Media_001', 'Abu Abdillah001', MEDIA_GROUP),
    ('Dawana_Media_002', 'Abdurafi', MEDIA_GROUP),
    ('Dawana_Media_003', 'Anonymous user', MEDIA_GROUP),
)


class Command(BaseCommand):
    help = (
        'Prepare eight dormant staff accounts with audited, least-privilege roles. '
        'Never creates passwords or grants access automatically.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--approved-by', default=None)

    def handle(self, *args, **options):
        for username, label, group in ACCOUNTS:
            self.stdout.write(f'{username} | {label or "Operations staff"} | {group}')
        if not options['apply']:
            self.stdout.write('PREVIEW ONLY: no database changes.')
            return

        User = get_user_model()
        approver_name = options.get('approved_by')
        approver = User.objects.filter(
            username=approver_name, is_active=True, is_superuser=True
        ).first() if approver_name else None
        if approver is None:
            raise CommandError('Supply --approved-by with an active owner superuser username.')

        with transaction.atomic():
            usernames = [item[0] for item in ACCOUNTS]
            # Abort rather than hijack an existing camper/staff identity.
            if User.objects.filter(username__in=usernames).exists():
                raise CommandError('One or more usernames already exist; no accounts created. Review collisions first.')
            if User.objects.filter(username__iexact='Operations_1').exclude(username='Operations_1').exists():
                raise CommandError('Case-insensitive username collision.')
            for username in usernames:
                if User.objects.filter(username__iexact=username).exists():
                    raise CommandError('Case-insensitive username collision; no accounts created.')

            # Production may have the 0042 recording table but lack the
            # post_migrate content type and its four model permissions.
            # Restore ONLY these metadata rows, never media or other grants.
            recording_ct, ct_created = ContentType.objects.get_or_create(
                app_label='dic', model='lecturerecording'
            )
            restored = []
            for code, name in (
                ('add_lecturerecording', 'Can add lecture recording'),
                ('change_lecturerecording', 'Can change lecture recording'),
                ('view_lecturerecording', 'Can view lecture recording'),
                ('publish_lecturerecording', 'Publish or withdraw lecture recordings'),
            ):
                _, created = Permission.objects.get_or_create(
                    content_type=recording_ct, codename=code, defaults={'name': name}
                )
                if created:
                    restored.append(code)
            if ct_created or restored:
                DICAdminAuditEvent.objects.create(
                    actor=approver, action='staff_permission_metadata_repaired',
                    target_type='ContentType', target_id=str(recording_ct.pk),
                    details={'model': 'dic.LectureRecording', 'content_type_created': ct_created,
                             'permissions_created': restored},
                )

            groups = {}
            for group_name in (OPERATIONS_GROUP, MEDIA_GROUP):
                grants = ROLES[group_name]
                permissions = []
                for grant in grants:
                    app_label, codename = grant.split('.', 1)
                    matches = Permission.objects.filter(
                        content_type__app_label=app_label, codename=codename
                    )
                    if matches.count() != 1:
                        raise CommandError(f'Missing or ambiguous permission: {grant}')
                    permissions.append(matches.get())
                group, created = Group.objects.get_or_create(name=group_name)
                group.permissions.add(*permissions)  # Additive, never remove prior grants.
                groups[group_name] = group
                DICAdminAuditEvent.objects.create(
                    actor=approver, action='staff_role_prepared',
                    target_type='Group', target_id=str(group.pk),
                    details={'name': group_name, 'created': created, 'grants': grants},
                )

            for username, label, group_name in ACCOUNTS:
                user = User(username=username, is_active=False, is_staff=True, is_superuser=False)
                user.set_unusable_password()
                # Display labels are not credentials and do not confer identity verification.
                if label:
                    user.first_name = label
                user.full_clean()
                user.save()
                user.groups.add(groups[group_name])
                DICAdminAuditEvent.objects.create(
                    actor=approver, action='staff_account_prepared',
                    target_type='User', target_id=str(user.pk),
                    details={'username': username, 'group': group_name,
                             'active': False, 'password_usable': False},
                )

        self.stdout.write(
            'Eight dormant accounts prepared. Owner must verify each real holder, '
            'set individual passwords privately through Django Admin, review permissions, '
            'then explicitly activate all eight accounts, including Dawana_Media_003. ' 
            'The Anonymous user label is display-only; issue credentials privately to its designated operator.'
        )
