# Additive link-only videos. No changes to registration or existing media bytes.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0044_studio_catalogue_placements'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name='studioasset', name='source_kind',
            field=models.CharField(max_length=24, choices=[
                ('photos', 'Photographs'), ('videos', 'Videos'), ('recordings', 'Lecture audio'),
                ('flyers', 'Flyers'), ('promotions', 'Promotions'), ('lecturers', 'Lecturers'),
                ('activities', 'Activities'), ('appearances', 'Lecturer appearances'),
                ('hosted', 'Hosted video and livestream')]),
        ),
        migrations.CreateModel(
            name='StudioHostedVideo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=300)),
                ('video_url', models.URLField(max_length=500)),
                ('lecturer', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True, max_length=5000)),
                ('state', models.CharField(max_length=12, choices=[
                    ('draft', 'Draft'), ('published', 'Published')], default='draft')),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('edition', models.ForeignKey(blank=True, null=True, to='dic.campedition',
                                             on_delete=django.db.models.deletion.PROTECT)),
                ('published_by', models.ForeignKey(blank=True, null=True, to=settings.AUTH_USER_MODEL,
                                                   related_name='+', on_delete=django.db.models.deletion.SET_NULL)),
            ],
            options={
                'ordering': ('-updated_at', '-pk'),
                'permissions': [('publish_studiohostedvideo', 'Publish YouTube/Vimeo links in Media Studio')],
            },
        ),
    ]
