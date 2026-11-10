"""Durable post-settlement ID work; HousingJob remains sole allocation queue."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CamperFulfillmentJob(models.Model):
    order = models.OneToOneField('dic.RegistrationOrder', on_delete=models.PROTECT,
                                 related_name='fulfillment_job')
    state = models.CharField(max_length=12, default='pending', choices=[
        ('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'),
        ('held', 'Staff review needed'), ('failed', 'Processing failed')])
    attempts = models.PositiveIntegerField(default=0)
    retry_at = models.DateTimeField(null=True, blank=True)
    reason_code = models.CharField(max_length=48, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=Q(state__in=[
            'pending', 'processing', 'completed', 'held', 'failed']), name='dic_fulfillment_state_valid')]
        indexes = [models.Index(fields=['state', 'created_at'], name='dic_fulfillment_queue_idx')]
