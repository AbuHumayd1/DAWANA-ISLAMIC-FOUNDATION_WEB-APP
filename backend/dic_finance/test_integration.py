"""Requires an explicitly approved disposable DB and migration plan excluding dic 0027."""
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError, PermissionDenied
from dic.models import CampEdition, DICAdminAuditEvent
from .models import Entry, Category, BudgetRevision
from .services import command, snapshot


class FinanceIntegrationTests(TestCase):
    def setUp(self):
        self.edition=CampEdition.objects.create(name='SYNTHETIC Finance tests',year=2026,
            camp_start_date=date(2026,12,23),camp_end_date=date(2027,1,1))
        self.creator=get_user_model().objects.create_user(username='finance-test-creator',is_staff=True,is_superuser=True)
        self.approver=get_user_model().objects.create_user(username='finance-test-approver',is_staff=True,is_superuser=True)
        self.category=command(self.edition,self.creator,dict(action='category',kind='expense',name='Synthetic test category',reason='Test only'))

    def create(self):
        return command(self.edition,self.creator,dict(action='create',category=self.category.pk,title='Synthetic expense',
            amount='10.00',date='2026-12-23',method='test',reference='synthetic-expense-1',evidence='Synthetic receipt reference',reason='Test'))

    def transition(self,entry,action,actor=None):
        return command(self.edition,actor or self.creator,dict(action=action,id=str(entry.pk),version=entry.version,reason='Synthetic test action'))

    def test_expense_approval_payment_reversal_and_audit(self):
        entry=self.create(); entry=self.transition(entry,'submit')
        with self.assertRaises(PermissionDenied): self.transition(entry,'approve')
        entry=self.transition(entry,'approve',self.approver)
        self.assertEqual(snapshot(self.edition,{})['summary']['expenditure_kobo'],0)
        entry=self.transition(entry,'pay')
        self.assertEqual(snapshot(self.edition,{})['summary']['expenditure_kobo'],1000)
        self.transition(entry,'reverse',self.approver)
        self.assertEqual(snapshot(self.edition,{})['summary']['expenditure_kobo'],0)
        self.assertEqual(Entry.objects.count(),1)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='finance_reverse').count(),1)

    def test_budget_revision_replaces_allocation_without_cash_effect(self):
        for amount in ['100.00','150.00']:
            command(self.edition,self.approver,dict(action='budget',category=self.category.pk,amount=amount,reason='Test revision'))
        self.assertEqual(BudgetRevision.objects.count(),2)
        totals=snapshot(self.edition,{})['summary']
        self.assertEqual(totals['approved_budget_kobo'],15000)
        self.assertEqual(totals['net_position_kobo'],0)

    def test_cross_edition_category_cannot_be_used(self):
        other=CampEdition.objects.create(name='Other synthetic edition',year=2025,
            camp_start_date=date(2025,12,23),camp_end_date=date(2026,1,1))
        with self.assertRaises(Category.DoesNotExist):
            command(other,self.creator,dict(action='budget',category=self.category.pk,amount='1.00',reason='Test denial'))

    def test_stale_version_and_unauthorised_action_do_not_write(self):
        entry=self.create(); stale_version=entry.version; entry=self.transition(entry,'submit')
        with self.assertRaises(ValidationError):
            command(self.edition,self.approver,dict(action='approve',id=str(entry.pk),version=stale_version,reason='Stale'))
        user=get_user_model().objects.create_user(username='finance-test-denied',is_staff=True)
        with self.assertRaises(PermissionDenied): self.transition(entry,'approve',user)
        entry.refresh_from_db(); self.assertEqual(entry.status,'submitted')
