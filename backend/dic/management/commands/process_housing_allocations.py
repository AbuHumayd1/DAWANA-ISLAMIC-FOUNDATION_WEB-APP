from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from dic.housing_queue import discover, claim, process_claim
from dic.housing_service import permitted


class Command(BaseCommand):
    help = 'Bounded LOCAL-FIRST housing worker; never starts a background service.'

    def add_arguments(self, parser):
        parser.add_argument('--edition', type=int, required=True)
        parser.add_argument('--actor', type=int, required=True, help='Authorized local staff user PK')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--discover-only', action='store_true')
        parser.add_argument('--database-name', required=True, help='Confirm the intended LOCAL development DB')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        name = str(db['NAME'])
        if (settings.SETTINGS_MODULE != 'config.settings.development'
                or db.get('HOST') not in ('127.0.0.1', 'localhost', '::1')
                or name != options['database_name'] or any(s in name.lower() for s in ('prod', 'stag'))
                or name in ('postgres', 'template0', 'template1')):
            raise CommandError('Refusing a non-confirmed local development database.')
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('Limit must be between 1 and 1000.')
        try:
            actor = get_user_model().objects.get(pk=options['actor'])
            permitted(actor, 'can_process_housing_queue')
            permitted(actor, 'can_allocate_participants')
        except (get_user_model().DoesNotExist, PermissionDenied):
            raise CommandError('An active staff actor with processing and allocation permissions is required.') from None
        from dic.models import CampEdition
        if not CampEdition.objects.filter(pk=options['edition']).exists():
            raise CommandError('Edition does not exist.')
        count = discover(options['edition'], actor, options['limit'])
        self.stdout.write(f'Discovered {count} new jobs; existing jobs preserved.')
        if options['discover_only']:
            return
        for _ in range(options['limit']):
            claimed = claim(options['edition'], actor)
            if not claimed:
                break
            state = process_claim(*claimed, actor)
            self.stdout.write(f'Job {claimed[0]}: {state}')
