from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from dic.models import (
    RegistrationRecoveryChallenge,
    RegistrationRecoveryGrant,
    RegistrationRecoveryRateLimit,
)


class Command(BaseCommand):
    help = "Remove expired DIC recovery challenges, grants, and rate-limit rows."

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(days=1)
        pending_deliveries_cleared = RegistrationRecoveryChallenge.objects.filter(
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
        grants_deleted, _ = RegistrationRecoveryGrant.objects.filter(
            expires_at__lt=cutoff
        ).delete()
        challenges_deleted, _ = RegistrationRecoveryChallenge.objects.filter(
            expires_at__lt=cutoff
        ).delete()
        limits_deleted, _ = RegistrationRecoveryRateLimit.objects.filter(
            updated_at__lt=cutoff
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                "Removed "
                f"{challenges_deleted} expired recovery challenge records, "
                f"{grants_deleted} recovery grant records, and "
                f"{limits_deleted} rate-limit records; "
                f"cleared {pending_deliveries_cleared} expired queued deliveries."
            )
        )
