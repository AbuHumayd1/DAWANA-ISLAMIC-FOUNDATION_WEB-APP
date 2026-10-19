"""Bounded, at-most-once portal OTP attempts using durable per-message claims.

A provider may accept a message before a process dies. Never reclaim a claimed
send: without provider idempotency, a lease retry can duplicate it. The visitor
can request a fresh challenge; expired/consumed claims are scrubbed by cleanup.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dic.models import ParticipantPortalChallenge
from dic.participant_api import primary_contact_matches
from dic.recovery import decrypt_delivery_payload, send_recovery_code, RecoveryDeliveryError, recovery_encryption_configured


def process_portal_challenge(challenge_id):
    with transaction.atomic():
        challenge = (ParticipantPortalChallenge.objects.select_for_update(of=("self",), skip_locked=True)
                     .select_related("order__primary_registrant").filter(pk=challenge_id).first())
        if challenge is None:
            return "skipped"
        if challenge.delivery_status != "queued":
            return "skipped"
        valid = (challenge.order and not challenge.consumed_at and challenge.expires_at > timezone.now()
                 and challenge.order.status != "cancelled" and challenge.order.access_token_revoked_at is None
                 and primary_contact_matches(challenge.order, challenge.channel, challenge.contact_digest))
        if not valid:
            challenge.delivery_status = "suppressed"
            challenge.encrypted_delivery_payload = ""
            challenge.save(update_fields=("delivery_status", "encrypted_delivery_payload"))
            return "suppressed"
        challenge.delivery_status = "processing"
        challenge.delivery_started_at = timezone.now()
        challenge.save(update_fields=("delivery_status", "delivery_started_at"))
        encrypted_payload = challenge.encrypted_delivery_payload
    # The claim commits before contacting a provider. No age-based reclamation.
    try:
        payload = decrypt_delivery_payload(encrypted_payload)
        send_recovery_code(payload["channel"], payload["destination"], payload["code"])
        status = "sent"
    except RecoveryDeliveryError:
        status = "failed"
    with transaction.atomic():
        current = ParticipantPortalChallenge.objects.select_for_update().get(pk=challenge_id)
        if current.delivery_status != "processing":
            return "skipped"
        if current.consumed_at or current.expires_at <= timezone.now():
            status = "suppressed"
        current.delivery_status = status
        current.encrypted_delivery_payload = ""
        current.delivery_started_at = None
        current.save(update_fields=("delivery_status", "encrypted_delivery_payload", "delivery_started_at"))
    return status


class Command(BaseCommand):
    help = "Deliver a bounded batch of participant-portal OTPs. Uncertain sends are never retried automatically."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        if not settings.DIC_RECOVERY_DELIVERY_WORKER_ENABLED or not recovery_encryption_configured():
            raise CommandError("Enable the configured recovery delivery worker and encryption before portal delivery.")
        limit = options["limit"]
        if not 1 <= limit <= 100:
            raise CommandError("Use --limit between 1 and 100.")
        queued = list(ParticipantPortalChallenge.objects.filter(
            delivery_status="queued", consumed_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("created_at").values_list("pk", flat=True)[:limit])
        counts = {}
        for challenge_id in queued:
            status = process_portal_challenge(challenge_id)
            counts[status] = counts.get(status, 0) + 1
        self.stdout.write(f"Participant delivery results: {counts}")
