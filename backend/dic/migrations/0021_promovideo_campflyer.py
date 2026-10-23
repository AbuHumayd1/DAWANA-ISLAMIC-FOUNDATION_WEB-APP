from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import dic.memory_storage
import dic.promo_storage


def moderation_fields():
    return [
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('state', models.CharField(choices=[('draft', 'Draft'), ('review', 'Ready for review'), ('published', 'Published')], default='draft', max_length=12)),
        ('featured', models.BooleanField(default=False)),
        ('display_order', models.PositiveIntegerField(default=0)),
        ('published_at', models.DateTimeField(blank=True, null=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('published_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
    ]


class Migration(migrations.Migration):
    dependencies = [('dic', '0020_lecturer_campactivity_lecturerappearance'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='PromoVideo',
            fields=moderation_fields() + [
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='promotional_videos', to='dic.campedition')),
                ('source_edition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='dic.campedition')),
                ('kind', models.CharField(choices=[('experience', 'Previous participant experience'), ('introduction', 'Upcoming edition introduction')], max_length=12)),
                ('title', models.CharField(max_length=200)),
                ('description', models.CharField(blank=True, max_length=400)),
                ('video', models.FileField(max_length=200, storage=dic.promo_storage.PrivatePromoStorage(), upload_to='', validators=[dic.promo_storage.validate_mp4])),
                ('poster', models.FileField(max_length=200, storage=dic.memory_storage.PrivateMemoryStorage(), upload_to='', validators=[dic.memory_storage.validate_photo])),
                ('alt_text', models.CharField(max_length=250)),
            ],
            options={'ordering': ('-featured', 'display_order', 'pk'), 'permissions': [('publish_promovideo', 'Can approve and publish DIC promotional videos')], 'abstract': False},
        ),
        migrations.CreateModel(
            name='CampFlyer',
            fields=moderation_fields() + [
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='official_flyers', to='dic.campedition')),
                ('title', models.CharField(max_length=200)),
                ('image', models.FileField(max_length=200, storage=dic.memory_storage.PrivateMemoryStorage(), upload_to='', validators=[dic.memory_storage.validate_photo])),
                ('alt_text', models.CharField(max_length=250)),
            ],
            options={'ordering': ('-featured', 'display_order', 'pk'), 'permissions': [('publish_campflyer', 'Can approve and publish official camp flyers')], 'abstract': False,
                     'constraints': [models.UniqueConstraint(condition=models.Q(state='published'), fields=('edition',), name='dic_one_published_flyer')]},
        ),
    ]
