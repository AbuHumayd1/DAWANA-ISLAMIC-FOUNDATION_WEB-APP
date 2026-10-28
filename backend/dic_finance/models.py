"""Finance records never replace registration payments or the scoring ledger."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Category(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=7, choices=[('income', 'Income'), ('expense', 'Expense')])
    active = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['edition', 'kind', 'name'], name='finance_category_unique'),
                       models.CheckConstraint(condition=Q(kind__in=['income', 'expense']), name='finance_category_kind')]


class Entry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    amount_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default='NGN')
    date = models.DateField()
    payee = models.CharField(max_length=160, blank=True)
    method = models.CharField(max_length=40)
    reference = models.CharField(max_length=100)
    evidence = models.TextField(blank=True, help_text='Private evidence/document reference; never a public receipt URL.')
    receipt = models.BinaryField(null=True, editable=False)
    receipt_type = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, default='draft', choices=[(s, s.title()) for s in
        ['draft', 'submitted', 'approved', 'paid', 'rejected', 'cancelled', 'reversed']])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    responsible = models.CharField(max_length=160, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = [(f'can_{action}_finance', label) for action, label in [
            ('view_details', 'View finance transaction details'), ('record_income', 'Record other income'),
            ('submit_expense', 'Submit expenses'), ('approve', 'Approve finance entries'),
            ('confirm_payment', 'Confirm expense payment'), ('manage_budget', 'Manage finance budgets and categories'),
            ('reconcile', 'Reconcile finance evidence'), ('export', 'Export finance reports')]]
        constraints = [models.CheckConstraint(condition=Q(amount_kobo__gt=0, currency='NGN'), name='finance_entry_money'),
            models.CheckConstraint(condition=Q(status__in=['draft','submitted','approved','paid','rejected','cancelled','reversed']), name='finance_entry_status'),
            models.UniqueConstraint(fields=['edition', 'reference'], name='finance_entry_reference_unique')]


class BudgetRevision(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    amount_kobo = models.PositiveBigIntegerField()
    reason = models.TextField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


class Reconciliation(models.Model):
    """Append-only provider evidence; never marks a PaymentAttempt successful."""
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    attempt = models.ForeignKey('dic.PaymentAttempt', on_delete=models.PROTECT)
    outcome = models.CharField(max_length=10, choices=[(s, s.title()) for s in ['matched','exception','refund','reversal']])
    provider_amount_kobo = models.PositiveBigIntegerField()
    reference = models.CharField(max_length=100)
    evidence = models.TextField()
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['edition','reference'], name='finance_reconcile_reference_unique'),
            models.CheckConstraint(condition=Q(outcome__in=['matched','exception','refund','reversal']), name='finance_reconcile_outcome')]
