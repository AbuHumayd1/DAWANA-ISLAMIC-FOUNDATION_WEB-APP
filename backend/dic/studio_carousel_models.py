"""Carousel publications are curated groups of existing, approved Studio media.

The models contain references, not copied media files. Public delivery rechecks
the live source's approval so withdrawn sources cannot leak through a carousel.
"""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from .memory_storage import private_memory_storage

CAROUSEL_FORMATS = (('images', 'Image carousel'), ('videos', 'Video carousel'),
                    ('mixed', 'Mixed media carousel'))
CAROUSEL_DESTINATIONS = (('foundation_home', 'Foundation homepage'),
                         ('foundation_archive', 'Foundation media archive'),
                         ('dic_landing', 'DIC landing page'),
                         ('dic_memories', 'DIC scrapbook'))


def validate_carousel_audio(value):
    if not value:
        return
    if value.size > 12 * 1024 * 1024 or value.size < 16:
        raise ValidationError('Audio must be between 16 bytes and 12 MB.')
    name = value.name.lower()
    if not name.endswith(('.mp3', '.ogg', '.wav')):
        raise ValidationError('Only MP3, OGG or WAV audio is supported.')
    original = value.tell()
    try:
        value.seek(0)
        signature = value.read(12)
        valid = (name.endswith('.mp3') and (signature.startswith(b'ID3') or signature[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'))) or (
            name.endswith('.ogg') and signature.startswith(b'OggS')) or (
            name.endswith('.wav') and signature.startswith(b'RIFF') and signature[8:12] == b'WAVE')
        if not valid:
            raise ValidationError('The audio signature does not match the file extension.')
    finally:
        value.seek(original)


class StudioCarousel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(max_length=5000, blank=True)
    format = models.CharField(max_length=12, choices=CAROUSEL_FORMATS)
    state = models.CharField(max_length=12, choices=(('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')), default='draft')
    soundtrack = models.FileField(storage=private_memory_storage, upload_to='studio-carousels/audio/%Y/%m/',
                                  blank=True, validators=[validate_carousel_audio])
    loop_audio = models.BooleanField(default=False)
    soundtrack_on_videos = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    published_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StudioCarouselSlide(models.Model):
    carousel = models.ForeignKey(StudioCarousel, related_name='slides', on_delete=models.CASCADE)
    asset = models.ForeignKey('dic.StudioAsset', on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField()
    caption = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ('order', 'pk')
        constraints = [models.UniqueConstraint(fields=('carousel', 'order'), name='dic_carousel_slide_order_unique')]


class StudioCarouselPlacement(models.Model):
    carousel = models.ForeignKey(StudioCarousel, related_name='placements', on_delete=models.CASCADE)
    destination = models.CharField(max_length=32, choices=CAROUSEL_DESTINATIONS)
    edition = models.ForeignKey('dic.CampEdition', null=True, blank=True, on_delete=models.PROTECT)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('carousel', 'destination'), name='dic_carousel_one_destination'),
        ]

    def clean(self):
        super().clean()
        scoped = self.destination.startswith('dic_')
        if scoped != bool(self.edition_id):
            raise ValidationError({'edition': 'DIC destinations require a selected edition; Foundation destinations do not.'})
