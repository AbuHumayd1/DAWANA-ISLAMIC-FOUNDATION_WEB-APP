from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dic.models import RegistrationRecoveryChallenge
from dic.recovery import (
    RecoveryDeliveryError,
    decrypt_delivery_payload,
    recovery_encryption_configured,
    send_recovery_code,
)
from dic.recovery_views import _matching_orders


def _claim_challenges(limit):
    now = timezone.now()
    stale_before = now - timedelta(
        seconds=settings.DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS + 60
    )
    queued = RegistrationRecoveryChallenge.DeliveryStatus.QUEUED
    processing = RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING
    RegistrationRecoveryChallenge.objects.filter(
        delivery_status=processing,
        delivery_started_at__lt=stale_before,
        expires_at__gt=now,
        consumed_at__isnull=True,
    ).update(
        delivery_status=queued,
        delivery_started_at=None,
    )
    with transaction.atomic():
        challenges = list(
            RegistrationRecoveryChallenge.objects.filter(
                delivery_status=queued,
                expires_at__gt=now,
                consumed_at__isnull=True,
            )
            .order_by("created_at")
            .select_for_update(skip_locked=True)[:limit]
        )
        for challenge in challenges:
            challenge.delivery_status = processing
            challenge.delivery_started_at = now
            challenge.delivery_attempts += 1
            challenge.save(
                update_fields=(
                    "delivery_status",
                    "delivery_started_at",
                    "delivery_attempts",
                )
            )
    return [challenge.pk for challenge in challenges]


def _finish_challenge(challenge_id, status):
    with transaction.atomic():
        challenge = (
            RegistrationRecoveryChallenge.objects.select_for_update()
            .filter(pk=challenge_id)
            .first()
        )
        if not challenge:
            return
        challenge.delivery_status = status
        challenge.encrypted_delivery_payload = ""
        challenge.delivery_started_at = None
        challenge.save(
            update_fields=(
                "delivery_status",
                "encrypted_delivery_payload",
                "delivery_started_at",
            )
        )


def _process_challenge(challenge_id):
    challenge = RegistrationRecoveryChallenge.objects.get(pk=challenge_id)
    if (
        challenge.delivery_status
        != RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING
        or challenge.consumed_at
        or challenge.expires_at <= timezone.now()
    ):
        _finish_challenge(
            challenge_id,
            RegistrationRecoveryChallenge.DeliveryStatus.SUPPRESSED,
        )
        return "suppressed"

    try:
        payload = decrypt_delivery_payload(challenge.encrypted_delivery_payload)
        order_ids = list(
            _matching_orders(
                payload["channel"],
                payload["destination"],
            ).values_list("pk", flat=True)
        )
        if not order_ids:
            _finish_challenge(
                challenge_id,
                RegistrationRecoveryChallenge.DeliveryStatus.SUPPRESSED,
            )
            return "suppressed"
        send_recovery_code(
            payload["channel"],
            payload["destination"],
            payload["code"],
        )
    except RecoveryDeliveryError:
        _finish_challenge(
            challenge_id,
            RegistrationRecoveryChallenge.DeliveryStatus.FAILED,
        )
        return "failed"

    with transaction.atomic():
        current = (
            RegistrationRecoveryChallenge.objects.select_for_update()
            .filter(pk=challenge_id)
            .first()
        )
        if (
            not current
            or current.delivery_status
            != RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING
            or current.consumed_at
            or current.expires_at <= timezone.now()
        ):
            _finish_challenge(
                challenge_id,
                RegistrationRecoveryChallenge.DeliveryStatus.SUPPRESSED,
            )
            return "suppressed"
        current.orders.set(order_ids)
        current.delivery_status = RegistrationRecoveryChallenge.DeliveryStatus.SENT
        current.encrypted_delivery_payload = ""
        current.delivery_started_at = None
        current.save(
            update_fields=(
                "delivery_status",
                "encrypted_delivery_payload",
                "delivery_started_at",
            )
        )
    return "sent"


class Command(BaseCommand):
    help = "Process a bounded batch of queued DIC recovery deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not settings.DIC_RECOVERY_DELIVERY_WORKER_ENABLED:
            raise CommandError(
                "DIC_RECOVERY_DELIVERY_WORKER_ENABLED must be enabled."
            )
        if not recovery_encryption_configured():
            raise CommandError(
                "DIC_RECOVERY_ENCRYPTION_KEY must be a valid Fernet key."
            )
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be greater than zero.")

        now = timezone.now()
        RegistrationRecoveryChallenge.objects.filter(
            delivery_status__in=(
                RegistrationRecoveryChallenge.DeliveryStatus.QUEUED,
                RegistrationRecoveryChallenge.DeliveryStatus.PROCESSING,
            ),
            expires_at__lte=now,
        ).update(
            delivery_status=RegistrationRecoveryChallenge.DeliveryStatus.FAILED,
            encrypted_delivery_payload="",
            delivery_started_at=None,
        )

        counts = {"sent": 0, "failed": 0, "suppressed": 0}
        for challenge_id in _claim_challenges(limit):
            result = _process_challenge(challenge_id)
            counts[result] += 1
        self.stdout.write(
            "DIC recovery delivery batch complete: "
            f"{counts['sent']} sent, {counts['failed']} failed, "
            f"{counts['suppressed']} suppressed."
        )
