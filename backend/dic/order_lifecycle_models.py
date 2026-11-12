"""Additive Phase A state; no record is expired merely by migrating."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class OrderExpiryPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    activated_at = models.DateTimeField(null=True)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=Q(id=1), name='dic_expiry_singleton')]


class OrderExpiry(models.Model):
    order = models.OneToOneField('dic.RegistrationOrder', on_delete=models.PROTECT, related_name='expiry_record')
    deadline = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    evidence_state = models.CharField(max_length=32)

    class Meta:
        default_permissions = ()
        permissions = [('manage_dic_order_lifecycle', 'Can activate order expiry and resolve late payments')]


class PaymentResolution(models.Model):
    request_id = models.UUIDField(default=uuid.uuid4, unique=True)
    attempt = models.ForeignKey('dic.PaymentAttempt', on_delete=models.PROTECT, related_name='resolutions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=24, choices=[('reinstate', 'Reinstate'),
        ('refund_requested', 'Refund requested'), ('refund_confirmed', 'Provider-confirmed refund')])
    reason = models.CharField(max_length=1000)
    provider_refund_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from django.core.exceptions import ValidationError
            raise ValidationError('Payment decisions are immutable audit records.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Payment decisions must be retained.')

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=('attempt', 'decision'), name='dic_resolution_decision_unique')]
