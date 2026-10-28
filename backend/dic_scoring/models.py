"""One immutable activity award linked to the existing house ledger."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ActivityAward(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    house = models.ForeignKey('dic.House', on_delete=models.PROTECT)
    participant = models.ForeignKey('dic.Participant', on_delete=models.PROTECT, null=True, blank=True)
    allocation = models.ForeignKey('dic.HouseAllocation', on_delete=models.PROTECT, null=True, blank=True)
    ledger_entry = models.OneToOneField('dic.HouseScoreTransaction', on_delete=models.PROTECT,
        related_name='activity_award')
    kind = models.CharField(max_length=10, choices=[('individual', 'Individual'), ('collective', 'Collective')])
    activity_code = models.CharField(max_length=80)
    activity_date = models.DateField()
    slot = models.CharField(max_length=80, blank=True)
    entitlement_key = models.CharField(max_length=180)
    exclusion_key = models.CharField(max_length=180, blank=True)
    cap_bucket = models.CharField(max_length=12, blank=True)
    evidence = models.JSONField(default=dict)
    submission_fingerprint = models.CharField(max_length=64)
    verified_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        default_permissions = ()
        ordering = ('-activity_date', '-pk')
        constraints = [
            models.CheckConstraint(condition=(
                Q(kind='individual', participant__isnull=False, allocation__isnull=False) |
                Q(kind='collective', participant__isnull=True, allocation__isnull=True)), name='dic_activity_kind_identity'),
            models.CheckConstraint(condition=Q(cap_bucket__in=('', 'service', 'character')), name='dic_activity_cap_bucket'),
            models.UniqueConstraint(fields=('edition', 'participant', 'entitlement_key'),
                condition=Q(kind='individual'), name='dic_activity_individual_unique'),
            models.UniqueConstraint(fields=('edition', 'house', 'entitlement_key'),
                condition=Q(kind='collective'), name='dic_activity_collective_unique'),
            models.UniqueConstraint(fields=('edition', 'participant', 'exclusion_key'),
                condition=~Q(exclusion_key=''), name='dic_activity_exclusion_unique'),
        ]
        indexes = [models.Index(fields=('edition', 'participant', 'activity_date'), name='dic_activity_person_day')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Activity awards are immutable. Reverse the linked ledger entry instead.')
        ledger = self.ledger_entry
        if (ledger.edition_id != self.edition_id or ledger.house_id != self.house_id
                or ledger.entry_type != 'award' or ledger.reverses_id):
            raise ValidationError('The original award must match its house ledger entry.')
        if self.participant_id and (self.allocation.participant_id != self.participant_id
                or self.allocation.edition_id != self.edition_id or self.allocation.house_id != self.house_id):
            raise ValidationError('The credited allocation must match the camper, edition and house.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Activity awards cannot be deleted. Use an audited reversal.')
