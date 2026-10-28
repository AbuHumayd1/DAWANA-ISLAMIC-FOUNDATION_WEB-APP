"""Prepared only: independent of postponed dic 0027."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('dic', '0026_house_score_transaction'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='RegistrationAssistance',
        fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('request_id', models.UUIDField(unique=True)),
            ('fingerprint', models.CharField(max_length=64)),
            ('actor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
            ('order', models.OneToOneField(to='dic.registrationorder', on_delete=django.db.models.deletion.PROTECT)),
            ('edition', models.ForeignKey(to='dic.campedition', on_delete=django.db.models.deletion.PROTECT)),
        ],
        options={'default_permissions': (), 'permissions': [('can_assist_registration', 'Create staff-assisted paid camper bookings')],
                 'constraints': [models.UniqueConstraint(fields=('edition', 'fingerprint'), name='assistance_edition_payload')]},
    )]
