"""Link-only Foundation videos: no binary uploads, no YouTube API or workers."""
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import models
from django.utils import timezone
from .video_providers import video_source


class StudioHostedVideo(models.Model):
    title = models.CharField(max_length=300)
    video_url = models.URLField(max_length=500)
    lecturer = models.CharField(max_length=200, blank=True)
    description = models.TextField(max_length=5000, blank=True)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT, null=True, blank=True)
    state = models.CharField(max_length=12, choices=(('draft', 'Draft'), ('published', 'Published')),
                             default='draft')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     related_name='+', on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at', '-pk')
        permissions = [('publish_studiohostedvideo', 'Publish YouTube/Vimeo links in Media Studio')]

    def clean(self):
        super().clean()
        try:
            video_source(self.video_url)
        except ValidationError as error:
            raise ValidationError({'video_url': error.messages}) from error

    def save(self, *args, actor=None, **kwargs):
        self.full_clean(exclude=('published_by', 'published_at'))
        if self.state == 'published':
            if not actor or not actor.is_active or not actor.is_staff or not actor.has_perm('dic.publish_studiohostedvideo'):
                raise PermissionDenied('Explicit Studio hosted video publishing permission required.')
            self.published_by = actor
            self.published_at = timezone.now()
        else:
            self.published_by = None
            self.published_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
