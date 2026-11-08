"""Bounded scheduling entry point; no payment provider calls or external broker."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from dic.housing_queue import discover, claim, process_claim
from dic.housing_service import permitted
from dic.models import CampEdition, PortalAccount
from dic.registration_accounts import process_verification_delivery
from dic.registration_guardians import approve_declared_guardians


class Command(BaseCommand):
    help = 'Process existing housing jobs and queued account verification delivery.'

    def add_arguments(self, parser):
        parser.add_argument('--edition', type=int, required=True)
        parser.add_argument('--actor', type=int, required=True)
        parser.add_argument('--database-name', required=True)
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        if getattr(settings, 'DAWANA_WEBSITE_ONLY', False):
            raise CommandError('Application processing is disabled in website-only mode.')
        if options['database_name'] != str(settings.DATABASES['default']['NAME']):
            raise CommandError('Database confirmation does not match.')
        if not 1 <= options['limit'] <= 100:
            raise CommandError('Limit must be between 1 and 100.')
        try:
            actor = get_user_model().objects.get(pk=options['actor'])
            permitted(actor, 'can_process_housing_queue')
            permitted(actor, 'can_allocate_participants')
        except (get_user_model().DoesNotExist, PermissionDenied):
            raise CommandError('An authorized housing processing actor is required.') from None
        if not CampEdition.objects.filter(pk=options['edition']).exists():
            raise CommandError('Edition does not exist.')
        approve_declared_guardians(options['edition'], actor, options['limit'])
        # Existing discovery repairs a missed historical handoff without resetting
        # held/failed jobs or a supervisor's release decision.
        discover(options['edition'], actor, options['limit'])
        counts = {}
        for _ in range(options['limit']):
            job = claim(options['edition'], actor)
            if not job:
                break
            state = process_claim(*job, actor)
            counts[state] = counts.get(state, 0) + 1
        accounts = list(PortalAccount.objects.filter(
            verification_delivery_at__lte=timezone.now(),
            bookings__order__edition_id=options['edition'], bookings__revoked_at__isnull=True,
        ).distinct().order_by('verification_delivery_at', 'pk').values_list('pk', flat=True)[:options['limit']])
        for account_id in accounts:
            state = 'email_' + process_verification_delivery(account_id)
            counts[state] = counts.get(state, 0) + 1
        self.stdout.write(str(counts))
