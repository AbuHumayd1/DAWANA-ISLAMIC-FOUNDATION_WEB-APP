# Additive Foundation Media Studio catalogue; no data mutation or implicit publication.
import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0043_exclude_dic2026_millionaire_drafts'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='StudioAsset',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('source_kind', models.CharField(max_length=24, choices=[
                    ('photos', 'Photographs'), ('videos', 'Videos'), ('recordings', 'Lecture audio'),
                    ('flyers', 'Flyers'), ('promotions', 'Promotions'), ('lecturers', 'Lecturers'),
                    ('activities', 'Activities'), ('appearances', 'Lecturer appearances')])),
                ('source_id', models.PositiveBigIntegerField()),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField(blank=True, max_length=5000)),
                ('album', models.CharField(blank=True, max_length=150)),
                ('campaign', models.CharField(blank=True, max_length=150)),
                ('programme', models.CharField(blank=True, max_length=150)),
                ('event', models.CharField(blank=True, max_length=150)),
                ('archived_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+')),
            ],
            options={'permissions': [
                ('manage_studio_assets', 'Manage Foundation media catalogue'),
                ('publish_studio_placements', 'Publish Foundation media placements'),
            ]},
        ),
        migrations.CreateModel(
            name='StudioPlacement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('destination', models.CharField(max_length=32, choices=[
                    ('foundation_archive', 'Foundation media archive'),
                    ('foundation_home', 'Foundation home'),
                    ('dic_memories', 'DIC memories gallery'),
                    ('dic_landing', 'DIC landing'),
                    ('dic_resources', 'DIC lecture resources'),
                    ('camper_resources', 'Camper Portal resources')])),
                ('state', models.CharField(max_length=12, default='draft',
                    choices=[('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')])),
                ('published_at', models.DateTimeField(null=True, blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('asset', models.ForeignKey(to='dic.studioasset', related_name='placements',
                    on_delete=django.db.models.deletion.PROTECT)),
                ('edition', models.ForeignKey(to='dic.campedition', null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT)),
                ('published_by', models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    null=True, blank=True, related_name='+',
                    on_delete=django.db.models.deletion.SET_NULL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='studioasset',
            constraint=models.UniqueConstraint(fields=('source_kind', 'source_id'), name='dic_studio_source_unique'),
        ),
        migrations.AddConstraint(
            model_name='studioasset',
            constraint=models.CheckConstraint(condition=Q(source_id__gt=0), name='dic_studio_source_positive'),
        ),
        migrations.AddConstraint(
            model_name='studioplacement',
            constraint=models.UniqueConstraint(fields=('asset', 'destination', 'edition'),
                                               name='dic_studio_destination_edition_unique'),
        ),
        migrations.AddConstraint(
            model_name='studioplacement',
            constraint=models.UniqueConstraint(fields=('asset', 'destination'),
                condition=Q(edition__isnull=True), name='dic_studio_global_destination_unique'),
        ),
    ]
