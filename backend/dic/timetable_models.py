"""The two edition-wide timetables. Publication is handled by timetable_services."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F


class TimetableEntry(models.Model):
    TYPES = [('activities', 'Daily Activities'), ('food', 'Food Timetable')]
    CERTAINTIES = [('confirmed', 'Confirmed'), ('proposed', 'Proposed'), ('unspecified', 'Unspecified')]
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    timetable_type = models.CharField(max_length=12, choices=TYPES)
    title = models.CharField(max_length=200, blank=True)
    lecturer = models.CharField(max_length=200, blank=True)
    audience = models.CharField(max_length=12, choices=[('all','General camp'),('talim',"Ta'lim: 5-9"),('tahdheeb','Tahdheeb: 10-15'),('dawah',"Da'wah: 16+"),('adults','Adults: 18+')], default='all')
    gender = models.CharField(max_length=6, choices=[('all','Everyone'),('male','Brothers'),('female','Sisters')], default='all')
    meal = models.CharField(max_length=10, blank=True, choices=[('breakfast','Breakfast'),('lunch','Lunch'),('dinner','Dinner')])
    date = models.DateField()
    day_number = models.PositiveSmallIntegerField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    time_label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    certainty = models.CharField(max_length=12, choices=CERTAINTIES, default='unspecified')
    location = models.CharField(max_length=200, blank=True)
    instructions = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=[('draft', 'Draft'), ('published', 'Published')], default='draft')
    source_key = models.CharField(max_length=100, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['date', 'display_order', 'pk']
        indexes = [models.Index(fields=['edition', 'timetable_type', 'date', 'status'], name='dic_tt_day_status_idx')]
        permissions = [('manage_dic_timetables', 'Edit DIC timetable drafts'), ('publish_dic_timetables', 'Publish and unpublish DIC timetables')]
        constraints = [
            models.UniqueConstraint(fields=['edition','date','meal'], condition=Q(timetable_type='food') & ~Q(meal=''), name='dic_food_date_meal_unique'),
            models.UniqueConstraint(fields=['edition', 'source_key'], condition=~Q(source_key=''), name='dic_tt_source_unique'),
            models.CheckConstraint(condition=Q(start_time__isnull=True) | Q(end_time__isnull=True) | Q(end_time__gt=F('start_time')), name='dic_tt_time_range'),
            models.CheckConstraint(condition=Q(timetable_type__in=['activities', 'food']), name='dic_tt_valid_type'),
            models.CheckConstraint(condition=Q(status__in=['draft', 'published']), name='dic_tt_valid_status'),
            models.CheckConstraint(condition=Q(day_number__gte=1), name='dic_tt_day_positive'),
            models.CheckConstraint(condition=Q(certainty__in=['confirmed', 'proposed', 'unspecified']), name='dic_tt_valid_certainty'),
        ]

    def clean(self):
        super().clean()
        if self.edition_id and self.date:
            if not self.edition.camp_start_date <= self.date <= self.edition.camp_end_date:
                raise ValidationError({'date': 'Date must fall within this camp edition.'})
            if self.day_number != (self.date - self.edition.camp_start_date).days + 1:
                raise ValidationError({'day_number': 'Day number must match the edition calendar.'})
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError('End time must follow start time; use a source label for open-ended periods.')
        if self.status == 'draft' and self.edition_id and self.date and not getattr(self, '_publication_action', False):
            if type(self).objects.filter(edition_id=self.edition_id, date=self.date,
                    timetable_type=self.timetable_type, status='published').exclude(pk=self.pk).exists():
                raise ValidationError('Unpublish this complete day before adding or editing drafts.')
        if self.start_time and self.end_time and self.edition_id and self.date:
            if type(self).objects.filter(edition_id=self.edition_id, date=self.date,
                    timetable_type=self.timetable_type, start_time__lt=self.end_time,
                    end_time__gt=self.start_time).exclude(pk=self.pk).filter(
                        Q(gender='all') | Q(gender=self.gender) if self.gender != 'all' else Q()
                    ).filter(Q(audience='all') | Q(audience=self.audience) | Q(audience__in=['dawah','adults']) if self.audience in ('dawah','adults') else (Q(audience='all') | Q(audience=self.audience) if self.audience != 'all' else Q())).exists():
                raise ValidationError('This time range overlaps another entry in this timetable and edition.')

    def save(self, *args, **kwargs):
        # Publication requires the transaction/permission boundary, never a form field.
        if not getattr(self, '_publication_action', False):
            if self.status != 'draft':
                raise ValidationError('Unpublish the day before editing. Use the publication action to publish.')
            if self.pk:
                previous = type(self).objects.get(pk=self.pk)
                if previous.status == 'published':
                    raise ValidationError('Unpublish the day before editing.')
                if (previous.edition_id, previous.timetable_type) != (self.edition_id, self.timetable_type):
                    raise ValidationError('Edition and timetable type are immutable; create a new draft entry.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.edition} / {self.get_timetable_type_display()} / {self.date} / {self.time_label}'
