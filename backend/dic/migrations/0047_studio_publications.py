from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import dic.memory_storage
import dic.studio_publication_models


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0046_aftercamp_assessments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudioCollection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160, unique=True)),
                ('slug', models.SlugField(max_length=170, unique=True)),
                ('description', models.CharField(blank=True, max_length=500)),
                ('kind', models.CharField(choices=[
                    ('programme', 'Programme or lecture series'), ('podcast', 'Podcast show')],
                    default='programme', max_length=12)),
                ('is_public', models.BooleanField(default=False)),
                ('display_order', models.PositiveIntegerField(default=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('display_order', 'title')},
        ),
        migrations.CreateModel(
            name='StudioPublication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[
                    ('article', 'Article'), ('document', 'PDF / research'),
                    ('event', 'Programme or event'), ('live', 'Live broadcast'),
                    ('podcast', 'Podcast episode'), ('video', 'Video link')], max_length=16)),
                ('title', models.CharField(max_length=250)),
                ('description', models.TextField(blank=True, max_length=3000)),
                ('body', models.TextField(blank=True, max_length=30000)),
                ('video_url', models.URLField(blank=True, max_length=500)),
                ('meeting_url', models.URLField(blank=True, max_length=500)),
                ('document', models.FileField(blank=True, max_length=220,
                    storage=dic.memory_storage.private_memory_storage,
                    upload_to='studio-publications/%Y/%m/',
                    validators=[dic.studio_publication_models.validate_public_pdf])),
                ('event_at', models.DateTimeField(blank=True, null=True)),
                ('live_state', models.CharField(choices=[
                    ('scheduled', 'Scheduled'), ('live', 'Live'), ('ended', 'Ended')],
                    default='scheduled', max_length=12)),
                ('season', models.PositiveSmallIntegerField(default=1)),
                ('episode', models.PositiveSmallIntegerField(default=1)),
                ('state', models.CharField(choices=[
                    ('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')],
                    default='draft', max_length=12)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('notified_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('collection', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='publications', to='dic.studiocollection')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-published_at', '-pk')},
        ),
    ]
