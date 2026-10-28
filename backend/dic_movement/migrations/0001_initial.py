"""Prepared, not applied. Does not depend on postponed dic 0027."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('dic', '0026_house_score_transaction'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='Movement',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
            ('kind', models.CharField(max_length=9, choices=[('departure', 'Departure'), ('return', 'Return')])),
            ('recorded_at', models.DateTimeField(auto_now_add=True)),
            ('reason', models.CharField(max_length=1000, blank=True)),
            ('authorization_reference', models.CharField(max_length=160, blank=True)),
            ('request_id', models.UUIDField()),
            ('sequence', models.PositiveIntegerField()),
            ('edition', models.ForeignKey(to='dic.campedition', on_delete=django.db.models.deletion.PROTECT)),
            ('participant', models.ForeignKey(to='dic.participant', on_delete=django.db.models.deletion.PROTECT)),
            ('recorded_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
        ],
        options={'default_permissions': (), 'permissions': [
            ('can_view_movements', 'View camper presence and movement history'),
            ('can_record_movements', 'Record camper departures and returns'),
            ('can_authorize_departure', 'Authorize and attest camper release')],
            'constraints': [
                models.UniqueConstraint(fields=('edition', 'request_id'), name='movement_edition_request'),
                models.UniqueConstraint(fields=('edition', 'participant', 'sequence'), name='movement_person_sequence'),
                models.CheckConstraint(condition=models.Q(sequence__gte=1), name='movement_sequence_positive'),
                models.CheckConstraint(condition=models.Q(kind__in=['departure', 'return']), name='movement_kind'),
                models.CheckConstraint(condition=~models.Q(kind='departure') | ~models.Q(authorization_reference=''), name='movement_departure_authority'),
            ]},
    )]
