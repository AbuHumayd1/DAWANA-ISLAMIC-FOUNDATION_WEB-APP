import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class RegistrationAssistance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order = models.OneToOneField('dic.RegistrationOrder', on_delete=models.PROTECT)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(unique=True)
    fingerprint = models.CharField(max_length=64)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Assistance creation audits are immutable.')
        if self.order.edition_id != self.edition_id:
            raise ValidationError('Assistance and booking must use the same edition.')
        return super().save(*args, **kwargs)

    class Meta:
        default_permissions = ()
        permissions = [('can_assist_registration', 'Create staff-assisted paid camper bookings')]
        constraints = [models.UniqueConstraint(fields=('edition', 'fingerprint'), name='assistance_edition_payload')]
