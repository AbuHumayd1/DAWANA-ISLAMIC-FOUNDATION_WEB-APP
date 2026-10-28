"""PROPOSED schema change. Do not apply without database approval."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0024_house_badge_colour'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name='CampCheckIn',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('checked_in_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('participant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='camp_check_ins', to='dic.participant')),
            ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='check_ins', to='dic.campedition')),
            ('checked_in_by', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='dic_check_ins', to=settings.AUTH_USER_MODEL)),
        ],
        options={
            'default_permissions': (),
            'permissions': [('can_check_in_dic_participants', 'Can check in DIC participants')],
            'constraints': [models.UniqueConstraint(fields=('participant', 'edition'), name='dic_checkin_participant_edition_unique')],
        },
    )]
