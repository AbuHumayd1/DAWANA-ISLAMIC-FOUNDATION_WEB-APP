"""Authoritative Finance calculations and permission-checked, audited commands."""
from datetime import date
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from dic.models import CampEdition, PaymentAttempt, DICAdminAuditEvent
from dic.payment_views import _revision_is_valid_at_payment
from .models import Category, Entry, BudgetRevision, Reconciliation


def require(actor, action=None):
    if not (actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.can_view_dic_operations') and actor.has_perm('dic.can_view_dic_finance')):
        raise PermissionDenied('Active Finance staff permission is required.')
    if action and not actor.has_perm(f'dic_finance.can_{action}_finance'):
        raise PermissionDenied('This finance action requires additional permission.')


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount * 100 != (amount * 100).to_integral_value() or amount > Decimal('9999999999.99'):
            raise ValueError
        return int(amount * 100)
    except (ValueError, InvalidOperation):
        raise ValidationError('Enter a positive NGN amount with at most two decimal places.')


def audit(actor, action, target, **details):
    DICAdminAuditEvent.objects.create(actor=actor, action='finance_' + action,
        target_type=target.__class__.__name__, target_id=str(target.pk), details=details)


def financial_totals(payments, records, budgets, edition_actual):
    income=sum(e['amount_kobo'] for e in records if e['kind']=='income' and e['status']=='approved')
    expense=sum(e['amount_kobo'] for e in records if e['kind']=='expense' and e['status']=='paid')
    revenue=sum(p['verified_kobo'] for p in payments)
    budget=sum(b['amount_kobo'] for b in budgets)
    gross=sum(p.get('gross_verified_kobo',p['verified_kobo']) for p in payments)
    adjustments=sum(p.get('adjustment_kobo',0) for p in payments)
    return dict(registration_revenue_kobo=revenue,other_income_kobo=income,expenditure_kobo=expense,
        gross_verified_collections_kobo=gross,recorded_adjustments_kobo=adjustments,
        net_verified_collections_kobo=revenue,
        available_operating_balance_kobo=None,
        approved_budget_kobo=budget,remaining_budget_kobo=budget-edition_actual,net_position_kobo=revenue+income-expense,
        approved_unpaid_kobo=sum(e['amount_kobo'] for e in records if e['kind']=='expense' and e['status']=='approved'),
        pending_attempts=sum(p['status'] in ['pending','initializing','init_unknown','verify_pending'] for p in payments),
        failed_attempts=sum(p['status']=='failed' for p in payments),exceptions=sum(bool(p['exception']) for p in payments))


def payment_reason(attempt, allow_refunded=False):
    """Reuse settlement timing/pricing checks; never weaken camper eligibility."""
    order = attempt.order
    if order.registration_basis != 'paid':
        return 'complimentary_registration_not_revenue'
    if order.payment_status == 'refunded' and not allow_refunded:
        return 'refunded'
    if order.status != 'confirmed' or order.payment_status not in (['paid','refunded'] if allow_refunded else ['paid']):
        return 'order_not_paid'
    revision = order.current_price_revision
    expected = int(order.total_amount_ngn * 100)
    if (attempt.status != 'successful' or not revision or revision.order_id != order.pk
            or not revision.accepted_at or attempt.price_revision_id != revision.pk
            or attempt.amount_kobo != expected or attempt.currency != 'NGN'
            or attempt.provider_status != 'success' or attempt.provider_reported_amount_kobo != expected
            or attempt.provider_reported_currency != 'NGN' or not attempt.provider_transaction_id
            or not attempt.verified_at or not attempt.provider_paid_at
            or not _revision_is_valid_at_payment(revision, attempt.provider_paid_at)):
        return 'unverified_evidence'
    return ''


def registration_rows(edition, filters, *, report_timezone=None, order_ids=None):
    attempts = PaymentAttempt.objects.filter(order__edition=edition).select_related('order__current_price_revision', 'price_revision').order_by('created_at','pk')
    if report_timezone:
        attempts = attempts.prefetch_related('order__current_price_revision__items')
    if order_ids is not None:
        attempts = attempts.filter(order_id__in=order_ids)
    if filters.get('category'):
        attempts = attempts.filter(order__items__category_id=filters['category']).distinct()
    # Receipt dates use provider completion time; unresolved attempts use creation date.
    rows, seen_orders, seen_provider = [], set(), set()
    review_orders = set(attempts.filter(status__in=['reconcile','amount_mismatch','duplicate_success']).values_list('order_id',flat=True))
    notes, histories = {}, {}
    for note in Reconciliation.objects.filter(edition=edition).order_by('created_at','pk'):
        notes[note.attempt_id] = note
        histories.setdefault(note.attempt_id,[]).append(dict(outcome=note.outcome,amount_kobo=note.provider_amount_kobo,
            reference=note.reference,evidence=note.evidence,reason=note.reason,actor_id=note.actor_id,date=note.created_at.isoformat()))
    for attempt in attempts:
        stamp = attempt.provider_paid_at or attempt.created_at
        day = timezone.localtime(stamp, ZoneInfo(report_timezone)).date() if report_timezone else stamp.date()
        if filters.get('date_from') and day < date.fromisoformat(filters['date_from']): continue
        if filters.get('date_to') and day > date.fromisoformat(filters['date_to']): continue
        reason = payment_reason(attempt)
        note = notes.get(attempt.pk)
        if attempt.order_id in review_orders: reason = reason or 'reconciliation_review'
        adjustment = 0
        documented_adjustments = sum(n['amount_kobo'] for n in histories.get(attempt.pk,[]) if n['outcome'] in ['refund','reversal'])
        if documented_adjustments:
            # Explicit documented partial/full refunds reduce a verified original charge.
            # A refunded order without trusted original evidence still contributes nothing.
            if not payment_reason(attempt,allow_refunded=True) and attempt.order_id not in review_orders:
                reason=''; adjustment=documented_adjustments
        if note and note.outcome=='exception': reason='exception'
        if not reason and (attempt.order_id in seen_orders or attempt.provider_transaction_id in seen_provider): reason = 'duplicate_receipt'
        gross = 0 if reason else attempt.amount_kobo
        received = max(0,gross-adjustment)
        if gross:
            seen_orders.add(attempt.order_id); seen_provider.add(attempt.provider_transaction_id)
        row = dict(id=str(attempt.pk), reference=attempt.reference, order=str(attempt.order.public_id),
            date=day.isoformat(), status=attempt.status, payment_status=attempt.order.payment_status,
            amount_kobo=attempt.amount_kobo, provider_amount_kobo=attempt.provider_reported_amount_kobo,
            provider_transaction_id=attempt.provider_transaction_id, verified_kobo=received,gross_verified_kobo=gross,
            adjustment_kobo=adjustment if gross else 0,
            excluded_reason=reason,
            exception=(reason if attempt.status in ['successful','reconcile','amount_mismatch','duplicate_success'] else '') or ('refund_or_reversal' if documented_adjustments else '') or (note.outcome if note and note.outcome=='exception' else ''), reconciliation=note.outcome if note else '', evidence=note.evidence if note else '')
        row['reconciliation_history'] = histories.get(attempt.pk,[])
        if filters.get('status') and row['status'] != filters['status']: continue
        if filters.get('payment_status') and row['payment_status'] != filters['payment_status']: continue
        if filters.get('q') and filters['q'].lower() not in (row['reference'] + row['order']).lower(): continue
        rows.append(row)
    return rows


def snapshot(edition, filters):
    payments = registration_rows(edition, filters)
    entries = Entry.objects.filter(edition=edition).defer('receipt').select_related('category','created_by','approved_by').order_by('-date','-created_at')
    for key, lookup in [('date_from','date__gte'),('date_to','date__lte'),('category','category_id'),('status','status')]:
        if filters.get(key) and key != 'category': entries = entries.filter(**{lookup:filters[key]})
    if filters.get('finance_category'): entries = entries.filter(category_id=filters['finance_category'])
    if filters.get('q'): entries = entries.filter(Q(title__icontains=filters['q']) | Q(reference__icontains=filters['q']))
    records = [dict(id=str(e.pk),kind=e.category.kind,category_id=e.category_id,category=e.category.name,
        title=e.title,description=e.description,amount_kobo=e.amount_kobo,currency=e.currency,date=e.date.isoformat(),
        payee=e.payee,method=e.method,reference=e.reference,evidence=e.evidence,status=e.status,
        responsible=e.responsible,recorded_by=e.created_by.get_username(),approved_by=e.approved_by.get_username() if e.approved_by else '',
        version=e.version,has_receipt=bool(e.receipt_type),created_at=e.created_at.isoformat(),updated_at=e.updated_at.isoformat()) for e in entries]
    budgets = {}
    history = []
    for rev in BudgetRevision.objects.filter(edition=edition).select_related('category','approved_by').order_by('created_at','pk'):
        item = dict(id=rev.pk,category_id=rev.category_id,category=rev.category.name,amount_kobo=rev.amount_kobo,
            reason=rev.reason,approved_by=rev.approved_by.get_username(),date=rev.created_at.isoformat())
        history.append(item); budgets[rev.category_id] = item.copy()
    # Budgets compare edition-wide actuals, independently of transaction search/date filters.
    all_expenses = Entry.objects.filter(edition=edition,category__kind='expense',status='paid')
    for category in Category.objects.filter(edition=edition,kind='expense'):
        budgets.setdefault(category.pk,dict(category_id=category.pk,category=category.name,amount_kobo=0,reason='No approved allocation'))
    for item in budgets.values():
        actual = sum(all_expenses.filter(category_id=item['category_id']).values_list('amount_kobo',flat=True))
        item.update(actual_kobo=actual,remaining_kobo=item['amount_kobo']-actual,
            utilisation_percent=round(actual*100/item['amount_kobo'],2) if item['amount_kobo'] else None,
            over_budget=actual>item['amount_kobo'])
    actual = sum(all_expenses.values_list('amount_kobo',flat=True))
    return dict(payments=payments,entries=records,budgets=list(budgets.values()),budget_history=history,
        summary=financial_totals(payments,records,list(budgets.values()),actual),
        categories=list(Category.objects.filter(edition=edition).values('id','name','kind','active')))


@transaction.atomic
def command(edition, actor, data):
    require(actor)
    if not isinstance(data, Mapping): raise ValidationError('Submit a financial action object.')
    if data.get('currency','NGN')!='NGN': raise ValidationError('Only NGN is supported.')
    # Serialize finance changes per edition, including cross-kind reference checks.
    CampEdition.objects.select_for_update().get(pk=edition.pk)
    action = data.get('action')
    previous_status = None
    reason = data.get('reason','')
    reason = reason.strip() if isinstance(reason,str) else ''
    if not reason: raise ValidationError('A justification is required.')
    if action == 'category':
        require(actor,'manage_budget')
        if data.get('kind') not in ['income','expense']: raise ValidationError('Choose income or expense.')
        name = str(data.get('name','')).strip()
        if not name or len(name)>100: raise ValidationError('Enter a category name (up to 100 characters).')
        target = Category.objects.create(edition=edition,name=name,kind=data['kind'])
    elif action == 'budget':
        require(actor,'manage_budget')
        category = Category.objects.get(pk=data.get('category'),edition=edition,kind='expense',active=True)
        target = BudgetRevision.objects.create(edition=edition,category=category,amount_kobo=money(data.get('amount')),reason=reason,approved_by=actor)
    elif action == 'create':
        category = Category.objects.get(pk=data.get('category'),edition=edition,active=True)
        require(actor,'record_income' if category.kind=='income' else 'submit_expense')
        reference = str(data.get('reference','')).strip()
        if not reference or len(reference)>100: raise ValidationError('A unique reference is required (maximum 100 characters).')
        if PaymentAttempt.objects.filter(Q(reference__iexact=reference)|Q(provider_transaction_id__iexact=reference)).exists():
            raise ValidationError('Registration payments cannot be recorded as other income or expenses.')
        if Entry.objects.filter(edition=edition,reference__iexact=reference).exists():
            raise ValidationError('This reference is already recorded.')
        title, method = str(data.get('title','')).strip(), str(data.get('method','')).strip()
        if not title or len(title)>160 or not method or len(method)>40: raise ValidationError('Enter a title and payment method within their length limits.')
        target = Entry.objects.create(edition=edition,category=category,title=title,method=method,
            amount_kobo=money(data.get('amount')),date=date.fromisoformat(data.get('date','')),reference=reference,
            description=str(data.get('description',''))[:10000],evidence=str(data.get('evidence',''))[:10000],
            payee=str(data.get('payee',''))[:160],responsible=str(data.get('responsible',''))[:160],created_by=actor)
    elif action == 'reconcile':
        require(actor,'reconcile')
        attempt = PaymentAttempt.objects.get(pk=data.get('attempt'),order__edition=edition)
        outcome = data.get('outcome')
        if outcome not in ['matched','exception','refund','reversal']: raise ValidationError('Invalid reconciliation outcome.')
        evidence, reference = str(data.get('evidence','')).strip(), str(data.get('reference','')).strip()
        if not evidence or not reference or len(reference)>100: raise ValidationError('Evidence and a unique reconciliation reference are required.')
        amount = money(data.get('amount'))
        if outcome=='matched' and (payment_reason(attempt) or amount != attempt.amount_kobo):
            raise ValidationError('Cannot match missing or inconsistent verified settlement evidence.')
        previous_adjustments=sum(Reconciliation.objects.filter(attempt=attempt,outcome__in=['refund','reversal']).values_list('provider_amount_kobo',flat=True))
        if outcome in ['refund','reversal'] and amount + previous_adjustments > attempt.amount_kobo:
            raise ValidationError('Cumulative refunds/reversals cannot exceed the original charge.')
        if outcome in ['refund','reversal'] and payment_reason(attempt,allow_refunded=True):
            raise ValidationError('A refund/reversal requires trusted evidence of the original charge.')
        target = Reconciliation.objects.create(edition=edition,attempt=attempt,outcome=outcome,
            provider_amount_kobo=amount,reference=reference,evidence=evidence,reason=reason,actor=actor)
    else:
        target = Entry.objects.select_for_update().get(pk=data.get('id'),edition=edition)
        previous_status = target.status
        if int(data.get('version',0)) != target.version: raise ValidationError('This entry changed. Refresh before retrying.')
        transitions = {'submit':('draft','submitted','record_income' if target.category.kind=='income' else 'submit_expense'),
            'approve':('submitted','approved','approve'), 'pay':('approved','paid','confirm_payment')}
        if action == 'receipt':
            require(actor,'record_income' if target.category.kind=='income' else 'submit_expense')
            if target.status!='draft' or target.created_by_id!=actor.pk: raise PermissionDenied('Only the creator may attach a receipt to a draft.')
            upload=data.get('receipt')
            if not hasattr(upload,'read') or not hasattr(upload,'size') or upload.size>2*1024*1024: raise ValidationError('Attach a PDF, PNG or JPEG up to 2 MB.')
            content=upload.read()
            kind='application/pdf' if content.startswith(b'%PDF-') else 'image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else ''
            if not kind: raise ValidationError('Unsupported receipt file type.')
            target.receipt=content; target.receipt_type=kind
        elif action in transitions:
            before, after, permission = transitions[action]; require(actor,permission)
            if target.status != before or (action=='pay' and target.category.kind!='expense'): raise ValidationError('Invalid workflow transition.')
            if action=='approve':
                if target.created_by_id==actor.pk: raise PermissionDenied('A different official must approve this entry.')
                target.approved_by=actor
            if action=='pay' and ((not target.evidence and not target.receipt_type) or not target.reference): raise ValidationError('Payment evidence is required before confirming expenditure.')
            target.status=after
        elif action in ['reject','cancel','reverse']:
            require(actor,'reconcile' if action=='reverse' else 'approve')
            allowed = ['approved','paid'] if action=='reverse' else ['draft','submitted']
            if target.status not in allowed: raise ValidationError('This action is not allowed for the current status.')
            target.status={'reject':'rejected','cancel':'cancelled','reverse':'reversed'}[action]
        else: raise ValidationError('Unknown finance action. Corrections require cancellation/reversal and a new entry.')
        target.version += 1
        target.save(update_fields=['status','approved_by','version','updated_at','receipt','receipt_type'])
    audit(actor,action,target,edition=edition.pk,reason=reason,status=getattr(target,'status',None),
        previous_status=previous_status,amount_kobo=getattr(target,'amount_kobo',getattr(target,'provider_amount_kobo',None)),
        reference=getattr(target,'reference',''),version=getattr(target,'version',None))
    return target
