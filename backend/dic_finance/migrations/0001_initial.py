"""Prepared only. Finance depends on dic 0026, never postponed dic 0027."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion as deletion


def fk(target, **kwargs):
    return models.ForeignKey(target,on_delete=deletion.PROTECT,**kwargs)


def base():
    return [('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('edition',fk('dic.campedition'))]


class Migration(migrations.Migration):
    initial=True
    dependencies=[('dic','0026_house_score_transaction'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='Category',fields=base()+[
            ('name',models.CharField(max_length=100)),('kind',models.CharField(max_length=7,choices=[('income','Income'),('expense','Expense')])),
            ('active',models.BooleanField(default=True))],options={'default_permissions':(), 'constraints':[
                models.UniqueConstraint(fields=('edition','kind','name'),name='finance_category_unique'),
                models.CheckConstraint(condition=models.Q(kind__in=['income','expense']),name='finance_category_kind')]}),
        migrations.CreateModel(name='Entry',fields=[
            ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('edition',fk('dic.campedition')),('category',fk('dic_finance.category')),
            ('title',models.CharField(max_length=160)),('description',models.TextField(blank=True)),
            ('amount_kobo',models.PositiveBigIntegerField()),('currency',models.CharField(max_length=3,default='NGN')),
            ('date',models.DateField()),('payee',models.CharField(max_length=160,blank=True)),
            ('method',models.CharField(max_length=40)),('reference',models.CharField(max_length=100)),
            ('evidence',models.TextField(blank=True,help_text='Private evidence/document reference; never a public receipt URL.')),
            ('receipt',models.BinaryField(null=True,editable=False)),('receipt_type',models.CharField(max_length=30,blank=True)),
            ('status',models.CharField(max_length=10,default='draft',choices=[(s,s.title()) for s in ['draft','submitted','approved','paid','rejected','cancelled','reversed']])),
            ('created_by',fk(settings.AUTH_USER_MODEL,related_name='+')),
            ('approved_by',fk(settings.AUTH_USER_MODEL,null=True,related_name='+')),
            ('responsible',models.CharField(max_length=160,blank=True)),('version',models.PositiveIntegerField(default=1)),
            ('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True))],
            options={'default_permissions':(), 'permissions':[(f'can_{action}_finance',label) for action,label in [
                ('view_details','View finance transaction details'),('record_income','Record other income'),
                ('submit_expense','Submit expenses'),('approve','Approve finance entries'),
                ('confirm_payment','Confirm expense payment'),('manage_budget','Manage finance budgets and categories'),
                ('reconcile','Reconcile finance evidence'),('export','Export finance reports')]],
                'constraints':[models.CheckConstraint(condition=models.Q(amount_kobo__gt=0,currency='NGN'),name='finance_entry_money'),
                    models.CheckConstraint(condition=models.Q(status__in=['draft','submitted','approved','paid','rejected','cancelled','reversed']),name='finance_entry_status'),
                    models.UniqueConstraint(fields=('edition','reference'),name='finance_entry_reference_unique')]}),
        migrations.CreateModel(name='BudgetRevision',fields=base()+[
            ('category',fk('dic_finance.category')),('amount_kobo',models.PositiveBigIntegerField()),
            ('reason',models.TextField()),('approved_by',fk(settings.AUTH_USER_MODEL,related_name='+')),
            ('created_at',models.DateTimeField(auto_now_add=True))],options={'default_permissions':()}),
        migrations.CreateModel(name='Reconciliation',fields=base()+[
            ('attempt',fk('dic.paymentattempt')),('outcome',models.CharField(max_length=10,choices=[(s,s.title()) for s in ['matched','exception','refund','reversal']])),
            ('provider_amount_kobo',models.PositiveBigIntegerField()),('reference',models.CharField(max_length=100)),
            ('evidence',models.TextField()),('reason',models.TextField()),('actor',fk(settings.AUTH_USER_MODEL,related_name='+')),
            ('created_at',models.DateTimeField(auto_now_add=True))],options={'default_permissions':(), 'constraints':[
                models.UniqueConstraint(fields=('edition','reference'),name='finance_reconcile_reference_unique'),
                models.CheckConstraint(condition=models.Q(outcome__in=['matched','exception','refund','reversal']),name='finance_reconcile_outcome')]})
    ]
