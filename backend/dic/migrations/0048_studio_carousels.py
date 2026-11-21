from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
import dic.memory_storage
import dic.studio_carousel_models


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0047_studio_publications'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='StudioCarousel',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField(max_length=5000, blank=True)),
                ('format', models.CharField(max_length=12, choices=[('images', 'Image carousel'), ('videos', 'Video carousel'), ('mixed', 'Mixed media carousel')])),
                ('state', models.CharField(max_length=12, choices=[('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')], default='draft')),
                ('soundtrack', models.FileField(storage=dic.memory_storage.private_memory_storage, upload_to='studio-carousels/audio/%Y/%m/', blank=True, validators=[dic.studio_carousel_models.validate_carousel_audio])),
                ('loop_audio', models.BooleanField(default=False)),
                ('published_at', models.DateTimeField(null=True, blank=True)),
                ('deleted_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+')),
            ],
        ),
        migrations.CreateModel(
            name='StudioCarouselSlide',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveSmallIntegerField()),
                ('caption', models.CharField(max_length=300, blank=True)),
                ('asset', models.ForeignKey(to='dic.studioasset', on_delete=django.db.models.deletion.PROTECT)),
                ('carousel', models.ForeignKey(to='dic.studiocarousel', related_name='slides', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={'ordering': ('order', 'pk')},
        ),
        migrations.CreateModel(
            name='StudioCarouselPlacement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('destination', models.CharField(max_length=32, choices=[
                    ('foundation_home', 'Foundation homepage'), ('foundation_archive', 'Foundation media archive'),
                    ('dic_landing', 'DIC landing page'), ('dic_memories', 'DIC scrapbook')])),
                ('published_at', models.DateTimeField(null=True, blank=True)),
                ('carousel', models.ForeignKey(to='dic.studiocarousel', related_name='placements', on_delete=django.db.models.deletion.CASCADE)),
                ('edition', models.ForeignKey(to='dic.campedition', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(model_name='studiocarouselslide',
            constraint=models.UniqueConstraint(fields=('carousel', 'order'), name='dic_carousel_slide_order_unique')),
        migrations.AddConstraint(model_name='studiocarouselplacement',
            constraint=models.UniqueConstraint(fields=('carousel', 'destination'), name='dic_carousel_one_destination')),
    ]
