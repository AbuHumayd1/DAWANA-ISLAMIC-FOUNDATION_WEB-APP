import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings


class Movement(models.Model):
    """Append-only physical movement; initial arrival remains CampCheckIn."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    participant = models.ForeignKey('dic.Participant', on_delete=models.PROTECT)
    kind = models.CharField(max_length=9, choices=[('departure', 'Departure'), ('return', 'Return')])
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000, blank=True)
    authorization_reference = models.CharField(max_length=160, blank=True)
    request_id = models.UUIDField()
    sequence = models.PositiveIntegerField()

    class Meta:
        default_permissions = ()
        permissions = [
            ('can_view_movements', 'View camper presence and movement history'),
            ('can_record_movements', 'Record camper departures and returns'),
            ('can_authorize_departure', 'Authorize and attest camper release'),
        ]
        constraints = [
            models.UniqueConstraint(fields=('edition', 'request_id'), name='movement_edition_request'),
            models.UniqueConstraint(fields=('edition', 'participant', 'sequence'), name='movement_person_sequence'),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name='movement_sequence_positive'),
            models.CheckConstraint(condition=models.Q(kind__in=['departure', 'return']), name='movement_kind'),
            models.CheckConstraint(condition=~models.Q(kind='departure') | ~models.Q(authorization_reference=''), name='movement_departure_authority'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Movement records are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Movement records must be retained.')
