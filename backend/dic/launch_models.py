from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F


class AcademicClass(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['edition', 'name'], name='dic_academic_name_unique')]
        permissions = [('manage_dic_classes', 'Manage approved academic classes and assignments')]

    def __str__(self): return f'{self.edition}: {self.name}'

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(edition_id=self.edition_id).exists():
            raise ValidationError('Class edition cannot be changed.')
        self.full_clean()
        return super().save(*args, **kwargs)


class AcademicAssignment(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    participant = models.ForeignKey('dic.Participant', on_delete=models.PROTECT)
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.PROTECT)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['edition', 'participant'], name='dic_academic_person_unique')]

    def clean(self):
        if self.academic_class_id and self.edition_id:
            if self.academic_class.edition_id != self.edition_id or not self.academic_class.active:
                raise ValidationError('Choose an active approved class in the same edition.')
        if self.participant_id and self.edition_id:
            from .models import RegistrationOrderItem
            if not RegistrationOrderItem.objects.filter(participant_id=self.participant_id, order__edition_id=self.edition_id).exclude(order__registration_basis='tutor').exists():
                raise ValidationError('Choose a camper registered in this edition; tutors cannot receive camper class assignments.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self): return f'{self.participant}: {self.academic_class}'


class CampAnnouncement(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    title = models.CharField(max_length=160)
    body = models.TextField(max_length=5000)
    status = models.CharField(max_length=12, choices=[('draft','Draft'),('published','Published')], default='draft')
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        permissions = [('manage_dic_announcements','Edit draft camp announcements'), ('publish_dic_announcements','Publish and unpublish camp announcements')]
        constraints = [models.CheckConstraint(condition=Q(starts_at__isnull=True)|Q(ends_at__isnull=True)|Q(ends_at__gt=F('starts_at')), name='dic_announcement_window'),
                       models.CheckConstraint(condition=Q(status__in=['draft','published']), name='dic_announcement_status')]

    def clean(self):
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError('Announcement end must follow its start.')

    def save(self, *args, **kwargs):
        if not getattr(self, '_publication_action', False):
            if self.status != 'draft' or self.pk and type(self).objects.filter(pk=self.pk, status='published').exists():
                raise ValidationError('Use the publication action; unpublish before editing.')
        if self.pk and type(self).objects.exclude(edition_id=self.edition_id).filter(pk=self.pk).exists():
            raise ValidationError('Announcement edition cannot be changed.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self): return self.title
