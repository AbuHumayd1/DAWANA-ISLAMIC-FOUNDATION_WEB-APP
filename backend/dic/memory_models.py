from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from .memory_storage import private_memory_storage, validate_photo


class MemoryActivity(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "Memory activity tags"

    def __str__(self):
        return self.name


class CampPhotograph(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Ready for review"
        PUBLISHED = "published", "Published"

    edition = models.ForeignKey("dic.CampEdition", on_delete=models.PROTECT, related_name="photographs")
    photograph = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200)
    activities = models.ManyToManyField(MemoryActivity, blank=True)
    caption = models.CharField(max_length=300)
    alt_text = models.CharField(max_length=250)
    featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-featured", "display_order", "pk")
        permissions = [("publish_campphotograph", "Can approve and publish camp photographs")]

    def __str__(self):
        return self.caption

    def save(self, *args, actor=None, **kwargs):
        if self.state == self.State.PUBLISHED:
            if actor is None or not actor.is_active or not actor.has_perm("dic.publish_campphotograph"):
                raise PermissionDenied("Explicit photo publication permission is required.")
            self.published_by = actor
            self.published_at = timezone.now()
        else:
            self.published_by = None
            self.published_at = None
        super().save(*args, **kwargs)


class CampVideo(models.Model):
    edition = models.ForeignKey("dic.CampEdition", on_delete=models.PROTECT, related_name="videos")
    video_url = models.URLField(max_length=500, help_text="Approved hosted links only. No video uploads or HTML.")
    thumbnail = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200)
    activities = models.ManyToManyField(MemoryActivity, blank=True)
    caption = models.CharField(max_length=300)
    alt_text = models.CharField(max_length=250)
    featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=12, choices=CampPhotograph.State.choices, default="draft")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-featured", "display_order", "pk")
        permissions = [("publish_campvideo", "Can approve and publish camp videos")]

    def __str__(self):
        return self.caption

    def clean(self):
        super().clean()
        from .video_providers import video_source
        from django.core.exceptions import ValidationError
        try:
            video_source(self.video_url)
        except ValidationError as exc:
            raise ValidationError({"video_url": exc.messages}) from exc

    def save(self, *args, actor=None, **kwargs):
        self.clean()
        if self.state == "published":
            if actor is None or not actor.is_active or not actor.has_perm("dic.publish_campvideo"):
                raise PermissionDenied("Explicit video publication permission is required.")
            self.published_by = actor
            self.published_at = timezone.now()
        else:
            self.published_by = None
            self.published_at = None
        super().save(*args, **kwargs)
