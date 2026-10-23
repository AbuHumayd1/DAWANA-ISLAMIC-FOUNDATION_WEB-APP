from django.core.exceptions import ValidationError
from django.db import models, transaction
from .memory_storage import private_memory_storage, validate_photo
from .promo_storage import private_promo_storage, validate_mp4
from .showcase_models import ModeratedShowcase


class PromoVideo(ModeratedShowcase):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT, related_name='promotional_videos')
    source_edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    kind = models.CharField(max_length=12, choices=[('experience', 'Previous participant experience'), ('introduction', 'Upcoming edition introduction')])
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=400, blank=True)
    video = models.FileField(storage=private_promo_storage, validators=[validate_mp4], max_length=200)
    poster = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200)
    alt_text = models.CharField(max_length=250)

    class Meta(ModeratedShowcase.Meta):
        abstract = False
        permissions = [('publish_promovideo', 'Can approve and publish DIC promotional videos')]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.kind == 'experience':
            if not self.source_edition_id:
                raise ValidationError({'source_edition': 'Select the previous camp edition.'})
            if self.edition_id and self.source_edition.year >= self.edition.year:
                raise ValidationError({'source_edition': 'Experience videos must come from a previous edition.'})
        if self.kind == 'introduction' and self.source_edition_id:
            raise ValidationError('Upcoming introductions do not have a previous source edition.')

    @transaction.atomic
    def save(self, *args, actor=None, **kwargs):
        # Serialize publication for this landing edition, including simultaneous admins.
        from .models import CampEdition
        CampEdition.objects.select_for_update().get(pk=self.edition_id)
        self.clean()
        if self.state == 'published':
            limit = 3 if self.kind == 'experience' else 2
            if type(self).objects.filter(edition_id=self.edition_id, kind=self.kind, state='published').exclude(pk=self.pk).count() >= limit:
                raise ValidationError(f'At most {limit} {self.kind} videos may be published for this edition.')
        super().save(*args, actor=actor, **kwargs)


class CampFlyer(ModeratedShowcase):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT, related_name='official_flyers')
    title = models.CharField(max_length=200)
    image = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200)
    alt_text = models.CharField(max_length=250)

    class Meta(ModeratedShowcase.Meta):
        abstract = False
        permissions = [('publish_campflyer', 'Can approve and publish official camp flyers')]
        constraints = [models.UniqueConstraint(fields=['edition'], condition=models.Q(state='published'), name='dic_one_published_flyer')]

    def __str__(self):
        return self.title
