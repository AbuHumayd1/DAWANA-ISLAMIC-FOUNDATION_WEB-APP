"""Prepare, but never activate, the owner-approved DIC 2026 certificate.

The original designer's corrected JPEG is a separately reviewed binary asset.
This command refuses to configure a mismatched or missing image.
"""
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dic.models import CampEdition, CertificateRelease

ARTWORK_NAME = 'DIC_2026_certificate_approved_artwork.jpg'
ARTWORK_SHA256 = 'bcbcf0615b11c7ebf7447de969b2f64966f7314d940a1377c2a628816cf60008'
RELEASE_LAGOS = datetime(2026, 12, 31, 21, 0, tzinfo=ZoneInfo('Africa/Lagos'))
# 842x651 points, matching the 3264x2522 designer artwork.
PAGE_WIDTH = 842
PAGE_HEIGHT = 651
NAME_BOX = [151, 281, 540, 54]
REFERENCE_BOX = [230, 15, 382, 25]
AUTHORITIES = (
    ('Shaykh AbdulHakeem Yuusuf Olomoda', 'Ameer, Da’wana Islamic Foundation'),
    ('Brother Abdullah Salman Akinola', 'Camp Director, Darul Islam Camp 2026'),
)


class Command(BaseCommand):
    help = 'Verify approved DIC 2026 artwork and prepare disabled release metadata.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Save the disabled configuration after verification.')

    def handle(self, *args, **options):
        artwork = Path(__file__).resolve().parents[2] / 'assets' / 'certificates' / ARTWORK_NAME
        if not artwork.is_file():
            raise CommandError(
                f'Approved designer JPEG missing: {artwork}. No database changes made. '
                'Install the exact approved binary asset before running this command.')
        actual = hashlib.sha256(artwork.read_bytes()).hexdigest()
        if actual != ARTWORK_SHA256:
            raise CommandError('Artwork SHA-256 mismatch; refusing to configure a changed design.')
        try:
            edition = CampEdition.objects.get(year=2026)
        except CampEdition.DoesNotExist as exc:
            raise CommandError('DIC 2026 edition is missing.') from exc
        config = CertificateRelease.objects.filter(edition=edition).first()
        if config and config.enabled:
            raise CommandError('Release already enabled; do not overwrite live release settings.')
        self.stdout.write('Verified designer artwork and named authorities:')
        for name, title in AUTHORITIES:
            self.stdout.write(f'  {name} — {title}')
        self.stdout.write(f'Release: {RELEASE_LAGOS.isoformat()} | artwork SHA-256: {actual}')
        if not options['apply']:
            self.stdout.write('DRY RUN only; no database change. Add --apply to configure a disabled release.')
            return
        with transaction.atomic():
            config, _ = CertificateRelease.objects.select_for_update().get_or_create(edition=edition)
            if config.enabled:
                raise CommandError('Release enabled during configuration; no changes committed.')
            config.artwork = ARTWORK_NAME
            config.artwork_sha256 = ARTWORK_SHA256
            config.page_width = PAGE_WIDTH
            config.page_height = PAGE_HEIGHT
            config.name_box = NAME_BOX
            config.reference_box = REFERENCE_BOX
            config.release_at = RELEASE_LAGOS
            config.enabled = False
            config.save()
        self.stdout.write(self.style.SUCCESS(
            'Configuration saved with enabled=False. Certificate issuance remains locked.'))
