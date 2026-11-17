"""Foundation-wide editorial catalogue: source object stored only once.

Placement references do not grant access to draft media or sensitive camper files.
Existing DIC media records remain authoritative for byte storage and publication.
"""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


SOURCE_KINDS = (
    ('photos', 'Photographs'), ('videos', 'Videos'), ('recordings', 'Lecture audio'),
    ('flyers', 'Flyers'), ('promotions', 'Promotions'), ('lecturers', 'Lecturers'),
    ('activities', 'Activities'),
)
DESTINATIONS = (
    ('foundation_archive', 'Foundation media archive'),
    ('foundation_home', 'Foundation home'),
    ('dic_memories', 'DIC memories gallery'),
    ('dic_landing', 'DIC landing'),
    ('dic_resources', 'DIC lecture resources'),
    ('camper_resources', 'Camper Portal resources'),
)
# Never allow public placement for recordings or participant-scoped content.
SUPPORTED_DESTINATIONS = {
    'photos': frozenset(('foundation_archive', 'foundation_home', 'dic_memories', 'dic_landing')),
    'videos': frozenset(('foundation_archive', 'foundation_home', 'dic_landing')),
    'recordings': frozenset(('dic_resources', 'camper_resources')),
    'flyers': frozenset(('foundation_archive', 'dic_landing')),
    'promotions': frozenset(('foundation_archive', 'foundation_home', 'dic_landing')),
    'lecturers': frozenset(('foundation_archive', 'dic_landing')),
    'activities': frozenset(('foundation_archive', 'dic_landing')),
}


class StudioAsset(models.Model):
    """Persistent index of a single existing validated Django model object."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_kind = models.CharField(max_length=24, choices=SOURCE_KINDS)
    source_id = models.PositiveBigIntegerField()
    title = models.CharField(max_length=300)
    description = models.TextField(max_length=5000, blank=True)
    album = models.CharField(max_length=150, blank=True)
    campaign = models.CharField(max_length=150, blank=True)
    programme = models.CharField(max_length=150, blank=True)
    event = models.CharField(max_length=150, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('source_kind', 'source_id'), name='dic_studio_source_unique'),
            models.CheckConstraint(condition=Q(source_id__gt=0), name='dic_studio_source_positive'),
        ]
        permissions = [('manage_studio_assets', 'Manage Foundation media catalogue'),
                       ('publish_studio_placements', 'Publish Foundation media placements')]

    def clean(self):
        if self.source_kind not in dict(SOURCE_KINDS):
            raise ValidationError({'source_kind': 'Unsupported editorial media type.'})


class StudioPlacement(models.Model):
    asset = models.ForeignKey(StudioAsset, related_name='placements', on_delete=models.PROTECT)
    destination = models.CharField(max_length=32, choices=DESTINATIONS)
    # DIC placement is scoped to an explicit edition, not inferred from upload.
    edition = models.ForeignKey('dic.CampEdition', null=True, blank=True, on_delete=models.PROTECT)
    state = models.CharField(max_length=12, choices=(
        ('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')),
        default='draft')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('asset', 'destination', 'edition'),
                                    name='dic_studio_destination_edition_unique'),
            # Database NULL comparisons do not enforce uniqueness; cover NULL separately.
            models.UniqueConstraint(fields=('asset', 'destination'),
                                    condition=Q(edition__isnull=True),
                                    name='dic_studio_global_destination_unique'),
        ]

    def clean(self):
        valid = SUPPORTED_DESTINATIONS.get(self.asset.source_kind, frozenset())
        if self.destination not in valid:
            raise ValidationError({'destination': 'This media type cannot be placed at that destination.'})
        scoped = self.destination.startswith('dic_') or self.destination == 'camper_resources'
        if scoped and not self.edition_id:
            raise ValidationError({'edition': 'Choose the exact DIC edition for this destination.'})
        if not scoped and self.edition_id:
            raise ValidationError({'edition': 'Foundation-wide destinations are not edition scoped.'})
        if self.asset.archived_at and self.state == 'published':
            raise ValidationError('Archived media cannot be published.')
