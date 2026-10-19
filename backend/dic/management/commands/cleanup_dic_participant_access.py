from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from dic.models import ParticipantPortalChallenge, ParticipantPortalGrant


class Command(BaseCommand):
    help = "Scrub expired OTP payloads and revoke expired portal grants in bounded batches; retain ID/audit evidence."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 5000:
            raise CommandError("Use --limit between 1 and 5000.")
        now = timezone.now()
        ids = list(ParticipantPortalChallenge.objects.filter(Q(expires_at__lte=now) | Q(consumed_at__isnull=False)).exclude(code_digest="", encrypted_delivery_payload="").values_list('pk', flat=True)[:limit])
        ParticipantPortalChallenge.objects.filter(pk__in=ids, delivery_status="processing").update(
            delivery_status="suppressed", delivery_started_at=None)
        scrubbed = ParticipantPortalChallenge.objects.filter(pk__in=ids).update(code_digest="", encrypted_delivery_payload="")
        grants = list(ParticipantPortalGrant.objects.filter(expires_at__lte=now, revoked_at__isnull=True).values_list('pk', flat=True)[:limit])
        revoked = ParticipantPortalGrant.objects.filter(pk__in=grants).update(revoked_at=now)
        self.stdout.write(f"Scrubbed {scrubbed} OTP records; revoked {revoked} expired grants.")
