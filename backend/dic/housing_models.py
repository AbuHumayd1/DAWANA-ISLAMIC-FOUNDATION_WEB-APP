"""Edition-scoped supervision and durable work, using the existing allocations."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class GuardianRelationship(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        REVOKED = 'revoked', 'Revoked'

    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    child = models.ForeignKey('dic.Participant', on_delete=models.PROTECT, related_name='housing_guardians')
    guardian = models.ForeignKey('dic.Participant', on_delete=models.PROTECT, related_name='housing_dependents')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField()
    registration_declared = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        permissions = [('can_approve_housing_guardians', 'Can approve or revoke housing guardians')]
        constraints = [
            models.UniqueConstraint(fields=['edition', 'child'], condition=Q(status__in=['pending', 'approved']), name='dic_one_current_guardian'),
            models.CheckConstraint(condition=~Q(child=models.F('guardian')), name='dic_guardian_not_child'),
            models.CheckConstraint(condition=Q(status__in=['pending', 'approved', 'rejected', 'revoked']), name='dic_guardian_status_valid'),
            models.CheckConstraint(condition=Q(status='pending') | (Q(reviewed_by__isnull=False) & Q(reviewed_at__isnull=False)), name='dic_guardian_review_required'),
            models.CheckConstraint(condition=~Q(status='approved') | (Q(approved_by__isnull=False) & Q(approved_at__isnull=False)), name='dic_guardian_approval_required'),
        ]

    def __str__(self):
        return f'{self.child} / {self.guardian} ({self.get_status_display()})'

    def clean(self):
        from .housing_policy import age_on
        from .models import HouseAllocation
        from .tutor_registration import is_tutor
        if self.edition_id and ((self.child_id and is_tutor(self.child_id, self.edition_id))
                or (self.guardian_id and is_tutor(self.guardian_id, self.edition_id))):
            raise ValidationError('Tutors cannot join camper housing or guardian accommodation groups.')
        if not self.pk and self.child_id and self.edition_id and HouseAllocation.objects.filter(
                edition_id=self.edition_id, participant_id=self.child_id, status='allocated').exists():
            raise ValidationError('Release the child’s existing group allocation before creating a guardian relationship.')
        if self.status in ('pending', 'approved') and self.edition_id and self.child_id and self.guardian_id:
            if age_on(self.child, self.edition) > 5:
                raise ValidationError('Dependent must be aged 0–5 on the edition reference date.')
            if self.guardian.sex.lower() != 'female' or age_on(self.guardian, self.edition) < 6:
                raise ValidationError('Guardian must be an independently accommodated female participant.')
            if self.guardian.eligible_for_dedicated_accommodation:
                raise ValidationError('Guardian has unresolved dedicated accommodation.')
        if not self.reason.strip():
            raise ValidationError('A supervisor review reason is required.')

    def save(self, *args, **kwargs):
        # Reviewed identities and transitions must go through the supervised service.
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, name) != getattr(self, name) for name in ('edition_id', 'child_id', 'guardian_id')):
                raise ValidationError('Guardian identities are immutable. Revoke and create a new relationship.')
            if old.approved_at and (old.approved_at != self.approved_at or old.approved_by_id != self.approved_by_id):
                raise ValidationError('Original guardian approval metadata is immutable.')
            if not getattr(self, '_supervised', False) and any(
                    getattr(old, name) != getattr(self, name)
                    for name in ('status', 'reason', 'reviewed_by_id', 'reviewed_at', 'approved_by_id', 'approved_at')):
                raise ValidationError('Use the housing supervisor review action.')
        elif self.status != self.Status.PENDING:
            raise ValidationError('New relationships must await supervisor approval.')
        self.full_clean()
        super().save(*args, **kwargs)


class HousingJob(models.Model):
    def save(self, *args, **kwargs):
        from .tutor_registration import is_tutor
        if self.participant_id and self.edition_id and is_tutor(self.participant_id, self.edition_id):
            raise ValidationError('Tutors cannot enter the camper housing queue.')
        return super().save(*args, **kwargs)

    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        HELD = 'held', 'Held for supervisor review'
        FAILED = 'failed', 'Failed; explicit retry required'

    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    participant = models.ForeignKey('dic.Participant', on_delete=models.PROTECT)
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    retry_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [('can_process_housing_queue', 'Can process and retry housing jobs')]
        constraints = [
            models.UniqueConstraint(fields=['edition', 'participant'], name='dic_housing_job_unique'),
            models.CheckConstraint(condition=Q(state__in=['pending', 'processing', 'completed', 'held', 'failed']), name='dic_housing_job_state_valid'),
        ]
        indexes = [models.Index(fields=['state', 'created_at'], name='dic_housing_queue_idx')]

    def __str__(self):
        return f'{self.participant} ({self.get_state_display()})'
