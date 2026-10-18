from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dic.models import CampEdition


OFFICIAL_DETAILS = {
    "name": "Daarul Islam Camp 2026",
    "year": 2026,
    "camp_start_date": date(2026, 12, 23),
    "camp_end_date": date(2027, 1, 1),
    "venue_name": "Faisal Omar Memorial School",
}


class Command(BaseCommand):
    help = (
        "Create the confirmed DIC 2026 edition as a draft listing without "
        "registration dates, fees, categories, or open registration."
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            edition = CampEdition.objects.select_for_update().filter(year=2026).first()
            if edition:
                mismatches = [
                    field
                    for field, expected in OFFICIAL_DETAILS.items()
                    if getattr(edition, field) != expected
                ]
                if mismatches:
                    raise CommandError(
                        "A DIC 2026 edition already exists with different confirmed "
                        "details; no changes were made. Review it in Django Admin."
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f"Existing edition {edition.pk} was left unchanged. "
                        f"Registration status: {edition.registration_status}."
                    )
                )
                return
            if CampEdition.objects.filter(is_active=True).exists():
                raise CommandError(
                    "Another camp edition is active. Review the edition configuration "
                    "in Django Admin; no changes were made."
                )
            edition = CampEdition.objects.create(
                **OFFICIAL_DETAILS,
                registration_status=CampEdition.RegistrationStatus.DRAFT,
                registration_open_date=None,
                registration_close_date=None,
                is_active=True,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created confirmed DIC 2026 edition {edition.pk} as a draft public "
                "listing. Registration remains closed; configure approved fees, "
                "deadline, and registration dates in Django Admin before opening."
            )
        )
