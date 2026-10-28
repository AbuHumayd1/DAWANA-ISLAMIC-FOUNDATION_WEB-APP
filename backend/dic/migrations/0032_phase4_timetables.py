"""Additive Phase 4 schema; included automatically in exact release manifests."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('dic', '0031_phase5_feedback_welfare'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='TimetableEntry',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('timetable_type', models.CharField(max_length=12, choices=[('activities', 'Daily Activities'), ('food', 'Food Timetable')])),
            ('date', models.DateField()),
            ('day_number', models.PositiveSmallIntegerField()),
            ('start_time', models.TimeField(null=True, blank=True)),
            ('end_time', models.TimeField(null=True, blank=True)),
            ('time_label', models.CharField(max_length=300)),
            ('description', models.TextField(blank=True)),
            ('certainty', models.CharField(max_length=12, choices=[('confirmed', 'Confirmed'), ('proposed', 'Proposed'), ('unspecified', 'Unspecified')], default='unspecified')),
            ('location', models.CharField(max_length=200, blank=True)),
            ('instructions', models.TextField(blank=True)),
            ('display_order', models.PositiveSmallIntegerField(default=0)),
            ('status', models.CharField(max_length=12, choices=[('draft', 'Draft'), ('published', 'Published')], default='draft')),
            ('source_key', models.CharField(max_length=100, blank=True, editable=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('published_at', models.DateTimeField(null=True, blank=True)),
            ('edition', models.ForeignKey(to='dic.campedition', on_delete=django.db.models.deletion.PROTECT)),
            ('modified_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name='+')),
            ('published_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name='+')),
        ],
        options={
            'ordering': ['date', 'display_order', 'pk'],
            'indexes': [models.Index(fields=['edition', 'timetable_type', 'date', 'status'], name='dic_tt_day_status_idx')],
            'permissions': [('manage_dic_timetables', 'Edit DIC timetable drafts'), ('publish_dic_timetables', 'Publish and unpublish DIC timetables')],
            'constraints': [
                models.UniqueConstraint(fields=['edition', 'source_key'], condition=~models.Q(source_key=''), name='dic_tt_source_unique'),
                models.CheckConstraint(condition=models.Q(start_time__isnull=True) | models.Q(end_time__isnull=True) | models.Q(end_time__gt=models.F('start_time')), name='dic_tt_time_range'),
                models.CheckConstraint(condition=models.Q(timetable_type__in=['activities', 'food']), name='dic_tt_valid_type'),
                models.CheckConstraint(condition=models.Q(status__in=['draft', 'published']), name='dic_tt_valid_status'),
                models.CheckConstraint(condition=models.Q(day_number__gte=1), name='dic_tt_day_positive'),
                models.CheckConstraint(condition=models.Q(certainty__in=['confirmed', 'proposed', 'unspecified']), name='dic_tt_valid_certainty'),
            ],
        },
    )]
