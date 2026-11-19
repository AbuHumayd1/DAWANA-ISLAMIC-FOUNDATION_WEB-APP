"""Additional camp coverage with strict plan-versus-outcome distinctions."""
from django.db.models import Case, F, IntegerField, Sum, Value, When
from .models import (AftercampAssessment, AcademicClass, AcademicAssignment,
                     CampAnnouncement, HouseScoreTransaction, TimetableEntry, House)
from . import reporting_services as reports


def _section(domain, title, metrics, charts=(), summary='', notes=()):
    return {'domain': domain, 'title': title, 'state': 'recorded',
            'metrics': metrics, 'charts': list(charts), 'summary': summary,
            'notes': list(notes)}


def _metric(label, number):
    from .aftercamp_reports import display
    return {'label':label, 'value':number, 'unit':'count', 'display': display(number)}


def _chart(title, rows):
    from .aftercamp_reports import display
    points = list(rows)[:20]
    scale = max((abs(float(p.get('value') or 0)) for p in points), default=0) or 1
    return {'title':title,'points':[
        {'label':str(p.get('label') or 'Not recorded')[:90],
         'value':p.get('value'),
         'width':round(abs(float(p.get('value') or 0))*100/scale,1),
         'display':display(p.get('value'))}
        for p in points]}


def additional_sections(edition, actor):
    """Aggregate existing persistent evidence, never infer work was completed."""
    sections = []
    if reports.storage(TimetableEntry):
        planned = TimetableEntry.objects.filter(edition=edition, status='published')
        activities = planned.filter(timetable_type='activities')
        meals = planned.filter(timetable_type='food')
        sections.append(_section('programme', 'Scheduled programme and camp activities', [
            _metric('Published activity entries', activities.count()),
            _metric('Days with published activity entries', activities.values('date').distinct().count()),
            _metric('Confirmed activity entries (schedule certainty)', activities.filter(certainty='confirmed').count()),
        ], summary='The published programme establishes what was scheduled, not what was actually delivered. Committee-confirmed delivery outcomes are recorded separately.',
            notes=['Published timetable entries are plans and schedules, not attendance registers or proof of delivery.']))
        sections.append(_section('catering', 'Scheduled catering and food service', [
            _metric('Published meal entries', meals.count()),
            _metric('Days with published meal entries', meals.values('date').distinct().count()),
        ], charts=[_chart('Published meal schedule', [
            {'label':m,'value':meals.filter(meal=m).count()}
            for m in ('breakfast','lunch','dinner')])],
            summary='The food timetable records meals scheduled for service. It does not measure meals served, catering expenditure, quality or satisfaction.',
            notes=['Actual meals served must be verified separately by authorized catering staff.']))
    else:
        for domain,title in [('programme','Scheduled programme and camp activities'),
                             ('catering','Scheduled catering and food service')]:
            sections.append({'domain':domain,'title':title,'state':'unavailable','metrics':[],
                             'charts':[],'summary':'The timetable evidence source is unavailable.',
                             'notes':[]})

    if (actor.has_perm('dic.can_view_dic_finance') and
            actor.has_perm('dic_finance.can_view_details_finance') and
            (not for_download or actor.has_perm('dic_finance.can_export_finance'))):
        from dic_finance.models import Entry
        if reports.storage(Entry):
            entries = Entry.objects.filter(edition=edition,currency='NGN')
            settled = entries.filter(status='paid')
            expenses = settled.filter(category__kind='expense')
            other_income = settled.filter(category__kind='income')
            approved_expenses = entries.filter(category__kind='expense',status='approved')
            expense_total = expenses.aggregate(total=Sum('amount_kobo'))['total'] or 0
            income_total = other_income.aggregate(total=Sum('amount_kobo'))['total'] or 0
            sections.append({'domain':'financial_operations',
                'title':'Recorded operational expenditure and other income',
                'state':'recorded',
                'metrics':[
                    {'label':'Paid expense entries','value':expenses.count(),'unit':'count',
                     'display':str(expenses.count())},
                    {'label':'Paid expenses (recorded)','value':expense_total,'unit':'NGN kobo',
                     'display':'₦{:,.2f}'.format(expense_total/100)},
                    {'label':'Other paid income entries','value':other_income.count(),'unit':'count',
                     'display':str(other_income.count())},
                    {'label':'Other paid income (recorded)','value':income_total,'unit':'NGN kobo',
                     'display':'₦{:,.2f}'.format(income_total/100)},
                    {'label':'Approved expenses pending recorded payment',
                     'value':approved_expenses.count(),'unit':'count',
                     'display':str(approved_expenses.count())},
                ],
                'charts':[],
                'summary':'Recorded paid expenses total ₦{:,.2f}; other paid income entries total ₦{:,.2f}. These entries are distinct from registration-payment verification and must not be added together without reconciliation.'.format(expense_total/100,income_total/100),
                'notes':['Only finance entries explicitly marked paid are counted as paid. Approved but unpaid expenses are reported separately.',
                         'This section is not an audited income statement or proof of bank settlement.'],
            })

    if actor.has_perm('dic.can_view_dic_scores') and reports.storage(HouseScoreTransaction):
        ledger = HouseScoreTransaction.objects.filter(edition=edition)
        totals = ledger.values('house__name').annotate(total=Sum(
            Case(When(entry_type='award',then=F('points')),default=-F('points'),
                 output_field=IntegerField()))).order_by('-total','house__name')
        rankings = [{'label':r['house__name'],'value':r['total']} for r in totals]
        from dic_scoring.models import ActivityAward
        if reports.storage(ActivityAward):
            awards = ActivityAward.objects.filter(edition=edition)
            activity_total = awards.count()
            activity_types = awards.values('activity_code').distinct().count()
        else:
            activity_total = None
            activity_types = None
        sections.append(_section('competitions', 'House championship and recorded scoring',[
            _metric('House scoring transactions',ledger.count()),
            _metric('Houses with recorded scoring',len(rankings)),
            _metric('Recorded activity awards',activity_total),
            _metric('Distinct scored activity codes',activity_types),
        ],charts=[_chart('Net house points',rankings)],
          summary='The scoring ledger provides recorded net house points, including deductions and reversals. Results are provisional unless the committee approves final standings.',
          notes=['Scoring does not prove competition attendance, learning outcomes or final awards.']))
    else:
        sections.append({'domain':'competitions','title':'House championship and recorded scoring',
                         'state':'restricted','metrics':[],'charts':[],
                         'summary':'Scoring totals require scoring-view permission or a configured ledger.','notes':[]})

    if actor.has_perm('dic.manage_dic_classes') and reports.storage(AcademicClass,AcademicAssignment):
        classes = AcademicClass.objects.filter(edition=edition)
        assignments = AcademicAssignment.objects.filter(edition=edition)
        sections.append(_section('teaching', 'Academic organization and teaching',[
            _metric('Configured academic classes', classes.count()),
            _metric('Assigned camper-class relationships', assignments.count()),
        ], summary='Academic classes and assignments demonstrate class organization only; they do not verify that lessons were delivered or that campers achieved learning outcomes.',
        notes=['Teaching delivery, Qur’an memorisation progress and assessment outcomes require verified teaching records.']))
    else:
        sections.append({'domain':'teaching','title':'Academic organization and teaching',
                         'state':'restricted','metrics':[],'charts':[],
                         'summary':'Academic class assignments are unavailable or restricted for this account.','notes':[]})

    if reports.storage(CampAnnouncement):
        announcements = CampAnnouncement.objects.filter(edition=edition)
        sections.append(_section('communications','Official camp communications', [
            _metric('Published camp announcements',announcements.filter(status='published').count()),
        ], summary='Published camp announcements record official communications, not proof that every camper received or read them.'))
    return sections


def approved_assessments(edition):
    if not reports.storage(AftercampAssessment):
        return []
    from .aftercamp_models import ASSESSMENT_TOPICS
    names = dict(ASSESSMENT_TOPICS)
    return [{'topic':row.topic,'title':names[row.topic],
             'findings':row.findings,'challenges':row.challenges,
             'recommendations':row.recommendations,'evidence_reference':row.evidence_reference,
             'approved_at':row.approved_at.isoformat() if row.approved_at else None}
            for row in AftercampAssessment.objects.filter(edition=edition,status='approved').order_by('topic')]


def editorial_drafts(edition, actor):
    if not getattr(actor,'is_superuser',False):
        return []
    if not reports.storage(AftercampAssessment):
        return []
    from .aftercamp_models import ASSESSMENT_TOPICS
    rows={x.topic:x for x in AftercampAssessment.objects.filter(edition=edition)}
    return [{'topic':key,'title':label,'status':rows[key].status if key in rows else 'empty',
             'findings':rows[key].findings if key in rows else '',
             'challenges':rows[key].challenges if key in rows else '',
             'recommendations':rows[key].recommendations if key in rows else '',
             'evidence_reference':rows[key].evidence_reference if key in rows else ''}
            for key,label in ASSESSMENT_TOPICS]
