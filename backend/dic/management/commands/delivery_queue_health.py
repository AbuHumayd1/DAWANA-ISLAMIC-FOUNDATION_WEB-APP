"""Read-only aggregate queue health; no addresses, tokens or delivery actions."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from dic.models import ParticipantPortalChallenge, RegistrationRecoveryChallenge


class Command(BaseCommand):
    help = 'Report aggregate OTP queue age; exits nonzero when dispatch is late.'

    def add_arguments(self, parser):
        parser.add_argument('--max-age-seconds', type=int, default=90)

    def handle(self, *args, **options):
        limit = options['max_age_seconds']
        if not 1 <= limit <= 300:
            raise CommandError('Use a queue-age threshold between 1 and 300 seconds.')
        now = timezone.now()
        overdue = False
        for label, model in [('portal', ParticipantPortalChallenge), ('recovery', RegistrationRecoveryChallenge)]:
            queue = model.objects.filter(delivery_status='queued', consumed_at__isnull=True, expires_at__gt=now)
            oldest = queue.order_by('created_at').values_list('created_at', flat=True).first()
            age = max(0, int((now - oldest).total_seconds())) if oldest else 0
            self.stdout.write(f'{label}: queued={queue.count()} oldest_seconds={age}')
            overdue = overdue or age > limit
        if overdue:
            raise CommandError('OTP dispatch age exceeds the approved threshold.')
