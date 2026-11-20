"""Programme collections, podcasts, broadcasts and written DAWANA publications.

New public editorial content is independent of camper-scoped media. Publishing
is explicitly staff authorised and a draft is never accessible publicly.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .video_providers import video_source
from .memory_storage import private_memory_storage


def validate_public_pdf(value):
    if value.size > 15 * 1024 * 1024 or value.size < 8:
        raise ValidationError('PDF must be between 8 bytes and 15 MB.')
    if not value.name.lower().endswith('.pdf'):
        raise ValidationError('Only PDF documents are supported.')
    position = value.tell()
    try:
        value.seek(0)
        if value.read(5) != b'%PDF-':
            raise ValidationError('File does not contain a valid PDF header.')
    finally:
        value.seek(position)


class StudioCollection(models.Model):
    title = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=170, unique=True)
    description = models.CharField(max_length=500, blank=True)
    kind = models.CharField(max_length=12, choices=(
        ('programme', 'Programme or lecture series'), ('podcast', 'Podcast show')),
        default='programme')
    is_public = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ('display_order', 'title')

    def __str__(self):
        return self.title


class StudioPublication(models.Model):
    kind = models.CharField(max_length=16, choices=(
        ('article', 'Article'), ('document', 'PDF / research'),
        ('event', 'Programme or event'), ('live', 'Live broadcast'),
        ('podcast', 'Podcast episode'), ('video', 'Video link')))
    collection = models.ForeignKey(StudioCollection, null=True, blank=True,
                                   related_name='publications', on_delete=models.PROTECT)
    title = models.CharField(max_length=250)
    description = models.TextField(max_length=3000, blank=True)
    body = models.TextField(max_length=30000, blank=True)
    video_url = models.URLField(max_length=500, blank=True)
    meeting_url = models.URLField(max_length=500, blank=True)
    document = models.FileField(storage=private_memory_storage, upload_to='studio-publications/%Y/%m/',\n                                blank=True, max_length=220, validators=[validate_public_pdf])
    event_at = models.DateTimeField(null=True, blank=True)
    live_state = models.CharField(max_length=12, choices=(
        ('scheduled', 'Scheduled'), ('live', 'Live'), ('ended', 'Ended')),
        default='scheduled')
    season = models.PositiveSmallIntegerField(default=1)
    episode = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=12, choices=(
        ('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')),
        default='draft')
    published_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-published_at', '-pk')

    def clean(self):
        super().clean()
        if self.state == 'published' and self.kind in ('video', 'podcast') and not self.video_url:
            raise ValidationError({'video_url': 'Add a YouTube or Vimeo link.'})
        if self.state == 'published' and self.kind == 'live' and not (self.video_url or self.meeting_url):
            raise ValidationError('Add a YouTube stream or Google Meet link.')
        if self.state == 'published' and self.kind == 'article' and not self.body.strip():
            raise ValidationError({'body': 'An article needs written content.'})
        if self.state == 'published' and self.kind == 'document' and not self.document:
            raise ValidationError({'document': 'Upload a PDF document.'})
        if self.kind == 'podcast' and self.collection_id and self.collection.kind != 'podcast':
            raise ValidationError({'collection': 'Podcast episodes belong to a podcast show.'})
        if self.video_url:
            try:
                video_source(self.video_url)
            except ValidationError as exc:
                raise ValidationError({'video_url': exc.messages}) from exc
        if self.meeting_url:
            try:
                url = urlsplit(self.meeting_url)
                if (url.scheme != 'https' or url.hostname != 'meet.google.com'
                        or url.username or url.password or url.port or url.fragment):
                    raise ValueError
            except ValueError:
                raise ValidationError({'meeting_url': 'Use a valid HTTPS Google Meet link.'}) from None
        if self.kind != 'podcast' and (self.season != 1 or self.episode != 1):
            raise ValidationError('Season and episode numbering is only for podcasts.')
        if self.state == 'published' and not self.published_at:
            raise ValidationError({'state': 'Publishing requires an explicit publication date.'})

    @property
    def visible(self):
        return self.state == 'published' and bool(self.published_at)

    def __str__(self):
        return self.title
