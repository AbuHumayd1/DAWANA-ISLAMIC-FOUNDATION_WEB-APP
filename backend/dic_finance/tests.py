"""Database-free Finance regression tests; ORM/concurrency acceptance remains separate."""
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from dic.operations_exports import spreadsheet_safe
from .services import money, require, payment_reason, registration_rows, command, financial_totals


class FinancePolicyTests(SimpleTestCase):
    def actor(self, allowed=True):
        return NS(pk=7,is_authenticated=True,is_active=True,is_staff=True,has_perm=lambda name:allowed)

    def attempt(self, **changes):
        revision=NS(pk=2,order_id=3,accepted_at=True)
        order=NS(pk=3,registration_basis='paid',payment_status='paid',status='confirmed',current_price_revision=revision,total_amount_ngn=Decimal('100'))
        value=NS(pk=4,order_id=3,order=order,status='successful',price_revision_id=2,amount_kobo=10000,currency='NGN',
            provider_status='success',provider_reported_amount_kobo=10000,provider_reported_currency='NGN',
            provider_transaction_id='provider-1',verified_at=True,provider_paid_at=True)
        for name,item in changes.items(): setattr(value,name,item)
        return value

    def test_money_exact_minor_units(self):
        self.assertEqual(money('123.45'),12345)
        self.assertEqual(money('0.01'),1)

    def test_money_rejects_nonfinite_negative_fractional_and_oversized(self):
        for value in ['NaN','Infinity','-1','0','0.001','10000000000','bad',None]:
            with self.subTest(value=value),self.assertRaises(ValidationError): money(value)

    def test_finance_requires_active_staff_operations_and_finance(self):
        with self.assertRaises(PermissionDenied): require(self.actor(False))
        for key in ['is_authenticated','is_active','is_staff']:
            user=self.actor(); setattr(user,key,False)
            with self.assertRaises(PermissionDenied): require(user)

    def test_action_permission_is_independent(self):
        user=self.actor(); user.has_perm=lambda name:name.startswith('dic.')
        require(user)
        with self.assertRaises(PermissionDenied): require(user,'approve')

    @patch('dic_finance.services._revision_is_valid_at_payment',return_value=True)
    def test_verified_receipt_uses_trusted_payment_evidence(self, valid):
        self.assertEqual(payment_reason(self.attempt()),'')
        valid.assert_called_once()

    def test_pending_failed_duplicate_and_mismatch_are_not_income(self):
        for status in ['pending','failed','duplicate_success','amount_mismatch','reconcile']:
            self.assertEqual(payment_reason(self.attempt(status=status)),'unverified_evidence')

    def test_refunded_and_cancelled_orders_are_excluded(self):
        attempt=self.attempt(); attempt.order.payment_status='refunded'
        self.assertEqual(payment_reason(attempt),'refunded')
        attempt.order.payment_status='paid'; attempt.order.status='cancelled'
        self.assertEqual(payment_reason(attempt),'order_not_paid')

    def test_missing_provider_id_or_amount_mismatch_is_exception(self):
        for changes in [dict(provider_transaction_id=''),dict(provider_reported_amount_kobo=1),dict(verified_at=None),dict(provider_reported_currency='USD')]:
            self.assertEqual(payment_reason(self.attempt(**changes)),'unverified_evidence')

    @patch('dic_finance.services._revision_is_valid_at_payment',return_value=False)
    def test_invalid_payment_timing_is_excluded(self, valid):
        self.assertEqual(payment_reason(self.attempt()),'unverified_evidence')

    def test_formula_injection_is_escaped_by_shared_export_utility(self):
        for text in ['=SUM(A1)','+cmd','-cmd','@cmd','\tformula','  =1']:
            self.assertTrue(spreadsheet_safe(text).startswith("'"))

    @patch('dic_finance.services.Reconciliation')
    @patch('dic_finance.services.PaymentAttempt')
    def test_duplicate_order_and_provider_credit_count_once(self, payments, reconciliation):
        from datetime import datetime, timezone
        attempt=self.attempt(reference='ref',created_at=datetime(2026,1,1,tzinfo=timezone.utc),provider_paid_at=datetime(2026,1,1,tzinfo=timezone.utc))
        attempt.order.public_id='booking'
        query=MagicMock(); query.__iter__.return_value=iter([attempt,attempt]); query.filter.return_value.values_list.return_value=[]
        payments.objects.filter.return_value.select_related.return_value.order_by.return_value=query
        reconciliation.objects.filter.return_value.order_by.return_value=[]
        with patch('dic_finance.services._revision_is_valid_at_payment',return_value=True):
            rows=registration_rows(NS(pk=1),{})
        self.assertEqual(sum(r['verified_kobo'] for r in rows),10000)
        self.assertEqual(rows[1]['exception'],'duplicate_receipt')
        payments.objects.filter.assert_called_once_with(order__edition=NS(pk=1))

    @patch('dic_finance.services.Reconciliation')
    @patch('dic_finance.services.PaymentAttempt')
    def test_documented_reversal_never_credits_revenue(self, payments, reconciliation):
        from datetime import datetime, timezone
        attempt=self.attempt(reference='ref',created_at=datetime(2026,1,1,tzinfo=timezone.utc),provider_paid_at=datetime(2026,1,1,tzinfo=timezone.utc)); attempt.order.public_id='booking'
        query=MagicMock(); query.__iter__.return_value=iter([attempt]); query.filter.return_value.values_list.return_value=[]
        payments.objects.filter.return_value.select_related.return_value.order_by.return_value=query
        note=NS(attempt_id=attempt.pk,outcome='reversal',evidence='document',provider_amount_kobo=10000,reference='rev',reason='bank reversal',actor_id=8,created_at=datetime(2026,1,1,tzinfo=timezone.utc))
        reconciliation.objects.filter.return_value.order_by.return_value=[note]
        with patch('dic_finance.services._revision_is_valid_at_payment',return_value=True): rows=registration_rows(NS(pk=1),{})
        self.assertEqual(rows[0]['verified_kobo'],0)
        self.assertEqual(rows[0]['exception'],'refund_or_reversal')

    @patch('dic_finance.services.audit')
    @patch('dic_finance.services.Entry')
    @patch('dic_finance.services.CampEdition')
    def test_creator_cannot_approve_own_expense(self, editions, entries, audit):
        entries.objects.select_for_update.return_value.get.return_value=NS(version=1,status='submitted',category=NS(kind='expense'),created_by_id=7)
        with self.assertRaises(PermissionDenied): command.__wrapped__(NS(pk=1),self.actor(),dict(action='approve',id='entry',version=1,reason='review'))
        audit.assert_not_called()

    @patch('dic_finance.services.audit')
    @patch('dic_finance.services.Entry')
    @patch('dic_finance.services.CampEdition')
    def test_approval_does_not_mark_expense_paid_and_is_audited(self, editions, entries, audit):
        target=NS(pk='entry',version=1,status='submitted',category=NS(kind='expense'),created_by_id=8,save=MagicMock())
        entries.objects.select_for_update.return_value.get.return_value=target
        command.__wrapped__(NS(pk=1),self.actor(),dict(action='approve',id='entry',version=1,reason='verified'))
        self.assertEqual(target.status,'approved'); self.assertEqual(target.version,2)
        audit.assert_called_once()

    @patch('dic_finance.services.Entry')
    @patch('dic_finance.services.CampEdition')
    def test_stale_workflow_version_is_rejected(self, editions, entries):
        entries.objects.select_for_update.return_value.get.return_value=NS(version=2,status='approved')
        with self.assertRaises(ValidationError): command.__wrapped__(NS(pk=1),self.actor(),dict(action='pay',id='entry',version=1,reason='test'))

    def test_api_rejects_anonymous_before_finance_storage(self):
        from rest_framework.test import APIRequestFactory
        from .api import FinanceView
        response=FinanceView.as_view()(APIRequestFactory().get('/api/v1/dic/operations/finance/?edition=1'))
        self.assertIn(response.status_code,[401,403])

    def test_budgets_and_approved_commitments_are_not_cash_expenses(self):
        totals=financial_totals([dict(verified_kobo=10000,status='successful',exception='')],
            [dict(kind='expense',status='approved',amount_kobo=5000)], [dict(amount_kobo=30000)],0)
        self.assertEqual(totals['net_position_kobo'],10000)
        self.assertEqual(totals['expenditure_kobo'],0)
        self.assertEqual(totals['approved_unpaid_kobo'],5000)
        self.assertEqual(totals['remaining_budget_kobo'],30000)

    def test_only_verified_income_and_paid_expense_count(self):
        entries=[dict(kind='income',status='approved',amount_kobo=3000),dict(kind='income',status='submitted',amount_kobo=90000),
            dict(kind='expense',status='paid',amount_kobo=2000),dict(kind='expense',status='reversed',amount_kobo=1000)]
        totals=financial_totals([],entries,[dict(amount_kobo=1500)],2000)
        self.assertEqual(totals['net_position_kobo'],1000)
        self.assertEqual(totals['remaining_budget_kobo'],-500)

    def test_pending_failed_attempts_are_counts_not_revenue(self):
        totals=financial_totals([dict(verified_kobo=0,status=s,exception='') for s in ['pending','failed']],[],[],0)
        self.assertEqual(totals['registration_revenue_kobo'],0)
        self.assertEqual(totals['pending_attempts'],1)
        self.assertEqual(totals['failed_attempts'],1)
