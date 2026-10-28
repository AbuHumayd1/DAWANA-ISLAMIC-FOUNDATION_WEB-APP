from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create or update the standard least-privilege DIC staff groups."

    GROUP_PERMISSIONS = {
        'DIC Administrators': ('view_campedition', 'view_registrationcategory', 'can_view_dic_operations'),
        "DIC Registration Staff": (
            "view_campedition",
            "view_registrationcategory",
            "view_registrationorder",
            "view_registrationorderitem",
            "view_participant",
            "view_houseallocation",
            "can_view_dic_operations",
            "can_export_dic_reports",
        ),
        "DIC Finance Reviewers": (
            "view_campedition",
            "view_registrationorder",
            "view_registrationorderitem",
            "view_registrationorderpriceitem",
            "view_paymentattempt",
            "view_paystackwebhookevent",
            "view_dicadminauditevent",
            "can_view_dic_operations",
            "can_view_dic_finance",
            "can_view_dic_audit",
            "can_export_dic_reports",
        ),
    }

    def add_arguments(self, parser):
        parser.add_argument('--apply-reviewed-grants', action='store_true',
            help='Explicitly apply the listed additive grants after reviewing existing access.')

    def handle(self, *args, **options):
        if not options.get('apply_reviewed_grants'):
            for name, codenames in self.GROUP_PERMISSIONS.items():
                self.stdout.write(name + ': ' + ', '.join(codenames))
            self.stdout.write('Preview only. Existing grants were not read or changed. Review sensitive inherited grants separately.')
            return
        with transaction.atomic():
            for name, codenames in self.GROUP_PERMISSIONS.items():
                group, created = Group.objects.get_or_create(name=name)
                permissions = list(
                    Permission.objects.filter(
                        content_type__app_label="dic",
                        codename__in=codenames,
                    )
                )
                found = {permission.codename for permission in permissions}
                missing = set(codenames) - found
                if missing:
                    raise CommandError(
                        f"Required DIC permissions are missing for {name}: "
                        f"{', '.join(sorted(missing))}. Run migrations first."
                    )
                # Preserve any explicitly granted granular permissions.
                group.permissions.add(*permissions)
                state = "Created" if created else "Updated"
                self.stdout.write(f"{state} {name} ({len(permissions)} permissions).")

