from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import Group,Permission
from django.contrib.auth import get_user_model
from django.db import transaction
from dic.staff_roles import ROLES
from dic.models import DICAdminAuditEvent
class Command(BaseCommand):
    help='Preview least-privilege committee roles. Explicit --apply and authorized superuser required; no automatic memberships.'
    def add_arguments(self,p):p.add_argument('--apply',action='store_true');p.add_argument('--approved-by')
    def handle(self,*args,**o):
        if not o['apply']:
            for name,grants in ROLES.items():self.stdout.write(name+': '+', '.join(grants))
            return
        actor=get_user_model().objects.filter(username=o['approved_by'],is_active=True,is_superuser=True).first()
        if not actor:raise CommandError('An active approving superuser is required.')
        with transaction.atomic():
            for name,grants in ROLES.items():
                permissions=[]
                for grant in grants:
                    app,code=grant.split('.')
                    permission=Permission.objects.filter(content_type__app_label=app,codename=code).first()
                    if not permission:raise CommandError('Missing declared permission: '+grant)
                    permissions.append(permission)
                group,_=Group.objects.get_or_create(name=name);group.permissions.add(*permissions)
                DICAdminAuditEvent.objects.create(actor=actor,action='committee_role_initialized',target_type='Group',target_id=str(group.pk),details={'permissions':grants})
        self.stdout.write('Roles initialized; no users or existing grants were removed or assigned.')
