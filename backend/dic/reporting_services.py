"""Read-only business reporting. Domain permissions precede every query.

Reports never call settlement, allocation, ID issuance or movement commands.
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.db import connection
from django.db.models import Count, Sum, Min, Q, F, OuterRef, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException
from .campsite_api import require_campsite_staff
from .models import (RegistrationOrder, RegistrationOrderItem, RegistrationCategory, Participant,
    CampCheckIn, House, HouseAllocation, HousingJob, PortalAccountBooking, PaymentAttempt,
    WelfareReport, WelfareEvent)

TZ=ZoneInfo('Africa/Lagos')
DOMAINS={
    'overview':('Operational overview',()),
    'registration':('Registration and demographics',()),
    'finance':('Verified payments',('dic.can_view_dic_finance',)),
    'accommodation':('Accommodation',('dic.view_house','dic.view_houseallocation')),
    'attendance':('QR arrival and movement',('dic_movement.can_view_movements','dic.can_check_in_dic_participants')),
    'academic':('Academic classes',()),
    'feedback':('Feedback and evaluations',('dic.can_view_dic_feedback',)),
    'welfare':('Welfare statistics',('dic.can_view_dic_welfare',)),
}


def require_report(actor, domain):
    require_campsite_staff(actor)
    if domain not in DOMAINS: raise ValidationError('Choose a supported report domain.')
    if not actor.has_perm('dic.can_export_dic_reports') or not all(actor.has_perm(p) for p in DOMAINS[domain][1]):
        raise PermissionDenied('Additional report-domain permission is required.')


def capabilities(actor):
    require_report(actor,'overview')
    return [{'id':key,'label':label} for key,(label,permissions) in DOMAINS.items()
        if all(actor.has_perm(p) for p in permissions)]


def filters(params, domain):
    result={key:str(params.get(key,'')).strip() for key in
        ('date_from','date_to','category','status','payment_status','q','channel','concern_category','urgency')}
    try:
        for key in ('date_from','date_to'):
            if result[key]: result[key]=date.fromisoformat(result[key]).isoformat()
        if result['date_from'] and result['date_to'] and result['date_from']>result['date_to']: raise ValueError
        if result['category'] and int(result['category'])<=0: raise ValueError
        page=int(params.get('page','1'))
        if page<1: raise ValueError
    except (ValueError,TypeError): raise ValidationError('Use valid dates, category and page numbers.')
    if len(result['q'])>100: raise ValidationError('Search is limited to 100 characters.')
    statuses={'overview':('submitted','confirmed','cancelled'), 'registration':('submitted','confirmed','cancelled'),
        'finance':tuple(PaymentAttempt.Status.values), 'accommodation':('active','reserve','inactive'),
        'attendance':('arrival','departure','return'), 'welfare':('new','review','resolved','closed')}
    if result['status'] and result['status'] not in statuses.get(domain,()): raise ValidationError('Choose a valid report status.')
    if result['payment_status'] and (domain!='finance' or result['payment_status'] not in RegistrationOrder.PaymentStatus.values):
        raise ValidationError('Payment status applies only to Finance reports.')
    if result['category'] and domain in ('feedback','welfare','academic'):
        raise ValidationError('Registration-category filtering is unavailable for this report; anonymous responses have no participant link.')
    if result['channel'] and (domain!='feedback' or result['channel'] not in ('daily','final','staff','lecturer')):
        raise ValidationError('Choose a valid feedback channel.')
    from .feedback_schema import CATEGORIES
    if result['concern_category'] and (domain!='welfare' or result['concern_category'] not in CATEGORIES):
        raise ValidationError('Choose a valid complaint category.')
    if result['urgency'] and (domain!='welfare' or result['urgency'] not in ('normal','urgent')):
        raise ValidationError('Choose a valid complaint urgency.')
    sort=params.get('sort','date')
    if sort not in ('date','-date','label','-label','value','-value','status','-status'):
        raise ValidationError('Choose a supported sort order.')
    result.update(page=page,sort=sort)
    return result


def period(query, field, selected):
    if selected['date_from']:
        query=query.filter(**{field+'__gte':datetime.combine(date.fromisoformat(selected['date_from']),time.min,TZ)})
    if selected['date_to']:
        end=date.fromisoformat(selected['date_to'])
        if end==date.max: raise ValidationError('Choose an earlier end date.')
        query=query.filter(**{field+'__lt':datetime.combine(end+timedelta(days=1),time.min,TZ)})
    return query


def storage(*models):
    tables=set(connection.introspection.table_names())
    return all(model._meta.db_table in tables for model in models)


def unavailable(message):
    return dict(available=False,state='Not Yet Configured',metrics=[],series={},rows=[],notes=[message])


def metric(label,value,description='',unit='count'):
    return dict(label=label,value=value,description=description,unit=unit)


def query_page(query,selected,sorting,tie_breaker):
    total=query.count()
    exporting=selected.get('_exporting',False)
    if exporting and total>5000: raise ValidationError('Narrow the export to 5,000 detail rows or fewer.')
    size=5000 if exporting else 50;page=1 if exporting else selected['page']
    key=selected['sort'].lstrip('-');field=sorting[key]
    ordering=('-' if selected['sort'].startswith('-') else '')+field
    query=query.order_by(ordering,tie_breaker)
    return query[(page-1)*size:page*size],dict(count=total,page=page,page_size=size)


def grouped(query, field, distinct=None):
    return [dict(label=str(row[field]) if row[field] is not None else 'Not recorded',value=row['total'])
        for row in query.order_by().values(field).annotate(total=Count(distinct or 'pk',distinct=bool(distinct))).order_by(field)]


def trends(query, field):
    return [dict(label=str(row['day']),value=row['total']) for row in query.order_by()
        .annotate(day=TruncDate(field,tzinfo=TZ)).values('day').annotate(total=Count('pk')).order_by('day')]


def scoped_items(edition, selected, registration_dates=True):
    query=RegistrationOrderItem.objects.filter(order__edition=edition,category__edition=edition)
    if selected['category']: query=query.filter(category_id=selected['category'])
    if registration_dates: query=period(query,'order__created_at',selected)
    return query


def trusted_paid_orders(orders):
    # Reuse the existing authoritative evidence predicate; no flag-only proof.
    from dic_finance.services import payment_reason
    from .models import PaymentAttempt
    blocked=PaymentAttempt.objects.filter(order_id__in=orders.values('pk'),status__in=('reconcile','amount_mismatch')).values('order_id')
    attempts=PaymentAttempt.objects.filter(order_id__in=orders.values('pk'),status='successful').exclude(order_id__in=blocked)
    attempts=attempts.select_related('order__current_price_revision').prefetch_related('order__current_price_revision__items')
    return {attempt.order_id for attempt in attempts.iterator(chunk_size=500) if not payment_reason(attempt)}


def registration(edition, selected, actor):
    items=scoped_items(edition,selected)
    if selected['status']: items=items.filter(order__status=selected['status'])
    # Reference-only search: names/contacts are not queried by general summaries.
    if selected['q']: items=items.filter(order__public_id__icontains=selected['q'])
    orders=RegistrationOrder.objects.filter(edition=edition,pk__in=items.values('order_id'))
    paid=orders.filter(registration_basis='paid'); tutors=items.filter(order__registration_basis='tutor')
    total=orders.count(); confirmed=orders.filter(status='confirmed').count()
    verified=trusted_paid_orders(paid)
    participant_count=items.values('participant_id').distinct().count()
    people=Participant.objects.filter(pk__in=items.values('participant_id'))
    age_counts=Counter()
    from .housing_policy import AGE_BANDS
    for birth in people.values_list('date_of_birth',flat=True).iterator(chunk_size=500):
        if birth is None or birth>edition.camp_start_date: label='Exact age not available'
        else:
            age=edition.camp_start_date.year-birth.year-((edition.camp_start_date.month,edition.camp_start_date.day)<(birth.month,birth.day))
            low,high=next((low,high) for low,high in AGE_BANDS if age>=low and (high is None or age<=high))
            label=f'{low}+' if high is None else f'{low}-{high}'
        age_counts[label]+=1
    multi=orders.annotate(item_count=Count('items')).filter(item_count__gt=1).count()
    # Portal account linking and approved housing guardians are distinct records.
    linked=PortalAccountBooking.objects.filter(order_id__in=orders.values('pk'),revoked_at__isnull=True).values('order_id').distinct().count()
    from .models import GuardianRelationship
    guardians=GuardianRelationship.objects.filter(edition=edition,status='approved',child_id__in=people.values('pk')).values('child_id').distinct().count()
    rows=[];pagination=None
    if actor.has_perm('dic.view_registrationorder'):
        rows=orders.annotate(value=Count('items')).values('public_id','created_at','status','payment_status','registration_basis','value')
        rows,pagination=query_page(rows,selected,{'date':'created_at','label':'public_id','value':'value','status':'status'},'pk')
        rows=[dict(label=str(row['public_id']),date=row['created_at'].astimezone(TZ).date().isoformat(),
            status=row['status'],recorded_payment_status=row['payment_status'],value=row['value'],
            basis=row['registration_basis']) for row in rows]
    return dict(available=True,metrics=[metric('Registered participants',participant_count),
        metric('Regular campers',items.filter(order__registration_basis='paid').values('participant_id').distinct().count()),
        metric('Tutor participants',tutors.values('participant_id').distinct().count()),metric('Bookings',total),
        metric('Confirmed bookings',confirmed),metric('Pending registrations',orders.filter(status='submitted').count()),
        metric('Cancelled bookings',orders.filter(status='cancelled').count()),metric('Trusted paid bookings',len(verified)),
        metric('Recorded failed-payment bookings',orders.filter(payment_status='failed').count()),
        metric('Recorded refunded bookings',orders.filter(payment_status='refunded').count()),
        metric('Duplicate participant sources',items.count()-participant_count),
        metric('Unverified or unpaid regular bookings',paid.exclude(pk__in=verified).exclude(status='cancelled').count()),
        metric('Multi-camper bookings',multi),metric('Portal-linked bookings',linked),metric('Approved housing guardian links',guardians),
        metric('Distinct contact records (not unique guardians)',orders.values('primary_registrant_id').distinct().count()),
        metric('Distinct linked portal accounts',PortalAccountBooking.objects.filter(order_id__in=orders.values('pk'),revoked_at__isnull=True).values('account_id').distinct().count()),
        metric('Distinct approved housing guardians',GuardianRelationship.objects.filter(edition=edition,status='approved',child_id__in=people.values('pk')).values('guardian_id').distinct().count()),
        metric('Confirmation rate',round(confirmed*100/total,2) if total else None,unit='percent'),
        metric('Verified payment conversion',round(len(verified)*100/paid.count(),2) if paid.exists() else None,unit='percent')],
        series={'Registration categories':grouped(items,'category_name_snapshot','participant_id'),
            'Gender distribution':grouped(people,'sex'),'Age at camp start':[dict(label=k,value=v) for k,v in sorted(age_counts.items())],
            'Registration trends':trends(orders,'created_at'),'Recorded payment states (not settlement proof)':grouped(orders,'payment_status')},rows=rows,row_pagination=pagination,
        notes=['Distinct participants and bookings use different denominators. Category totals may overlap when duplicate sources exist.',
            'Age uses collected DOB only, at camp start, with existing housing-policy band boundaries; it does not allocate classes or certify housing.',
            'Confirmed status is not a completeness or portal-eligibility certificate. Payment evidence reuses Finance checks; source/identity review remains separate.',
            'Booking contacts, explicit portal links and approved housing guardian relationships are reported separately; no guardian relationship is inferred.'])


def financial_fold(rows):
    return dict(gross=sum(row['gross_verified_kobo'] for row in rows),refunds=sum(row['adjustment_kobo'] for row in rows),
        net=sum(row['verified_kobo'] for row in rows),exceptions=sum(bool(row['exception']) for row in rows),
        successful=sum(row['gross_verified_kobo']>0 for row in rows),
        pending=sum(row['status'] in ('pending','initializing','init_unknown','verify_pending') for row in rows),
        failed=sum(row['status']=='failed' for row in rows))


def finance(edition, selected, actor):
    from dic_finance.models import Reconciliation
    from dic_finance.services import registration_rows
    from .models import PaymentAttempt, RegistrationOrderPriceItem
    if not storage(Reconciliation): return unavailable('Finance reconciliation schema awaits approved application; financial totals are unavailable.')
    orders=RegistrationOrder.objects.filter(edition=edition,registration_basis='paid')
    if selected['category']: orders=orders.filter(items__category_id=selected['category']).distinct()
    if selected['status']: orders=orders.filter(payment_attempts__status=selected['status']).distinct()
    if selected['payment_status']: orders=orders.filter(payment_status=selected['payment_status'])
    if selected['q']: orders=orders.filter(Q(public_id__icontains=selected['q'])|Q(payment_attempts__reference__icontains=selected['q'])).distinct()
    if PaymentAttempt.objects.filter(order_id__in=orders.values('pk')).count()>20000:
        raise ValidationError('Narrow the edition/category/status filters to at most 20,000 attempts.')
    data=registration_rows(edition,{key:selected[key] for key in ('date_from','date_to','status','q')},
        report_timezone='Africa/Lagos',order_ids=orders.values('pk'))
    totals=financial_fold(data)
    # Apportion nothing: actual accepted revision line fees account for gross
    # collections. Booking-level adjustments have no invented per-child split.
    credited={row['order']:row for row in data if row['gross_verified_kobo']}
    categories=Counter();unattributed=0
    lines=RegistrationOrderPriceItem.objects.filter(revision__order__edition=edition,
        revision_id=F('revision__order__current_price_revision_id'),revision__order__public_id__in=credited)
    for row in lines.values('category_name_snapshot').annotate(total=Sum('fee_snapshot_ngn')):
        categories[row['category_name_snapshot']]+=int(row['total']*100)
    attributed=sum(categories.values());unattributed=totals['gross']-attributed
    trend=Counter()
    for row in data: trend[row['date']]+=row['verified_kobo']
    details=actor.has_perm('dic_finance.can_view_details_finance')
    rows=[dict(label=row['order'],date=row['date'],status=row['status'],recorded_payment_status=row['payment_status'],
        value=row['verified_kobo'],attempt_id=row['id'],reference=row['reference'],gross_kobo=row['gross_verified_kobo'],recorded_adjustment_kobo=row['adjustment_kobo'],
        exception=row['exception'],excluded_reason=row['excluded_reason']) for row in data] if details else []
    expected=period(orders,'created_at',selected).aggregate(total=Sum('total_amount_ngn'))['total']
    recorded_adjustments=Reconciliation.objects.filter(edition=edition,attempt__order_id__in=orders.values('pk'),outcome__in=('refund','reversal'))
    recorded_adjustments=period(recorded_adjustments,'created_at',selected).aggregate(total=Sum('provider_amount_kobo'))['total'] or 0
    return dict(available=True,metrics=[metric('Expected booking value',int((expected or Decimal(0))*100),unit='NGN kobo'),
        metric('Gross verified collections',totals['gross'],unit='NGN kobo'),metric('Applied recorded adjustments',totals['refunds'],unit='NGN kobo'),
        metric('Recorded adjustment events in period',recorded_adjustments,unit='NGN kobo'),metric('Net verified collections',totals['net'],unit='NGN kobo'),
        metric('Verified charges',totals['successful']),metric('Pending attempts',totals['pending']),metric('Failed attempts',totals['failed']),
        metric('Exceptional attempts',totals['exceptions']),metric('Gross / accepted-price discrepancy',unattributed,unit='NGN kobo')],
        series={'Net verified collections by payment day (kobo)':[dict(label=k,value=v) for k,v in sorted(trend.items())],
            'Gross collections by accepted price category (kobo)':[dict(label=k,value=v) for k,v in sorted(categories.items())]},rows=rows,
        notes=['Not settled bank revenue. Trusted Finance evidence, duplicate-charge exclusion and documented adjustments are reused unchanged.',
            'Expected value uses booking creation dates and matching booking cohort; collections use provider completion dates and matching attempt status/search. Adjustments applied to charges include documented later adjustments; adjustment events use their recorded dates.',
            'Category filtering selects whole bookings. Category gross uses actual accepted revision lines, including siblings; refunds are not allocated to children without supporting records.',
            'Reconciliation documents, provider IDs, credentials and personal contacts are never returned by this endpoint.'])


def accommodation(edition, selected, actor):
    if not storage(House,HouseAllocation,HousingJob): return unavailable('Accommodation schema awaits approved application.')
    items=scoped_items(edition,selected,registration_dates=False)
    tutor_ids=RegistrationOrderItem.objects.filter(order__edition=edition,order__registration_basis='tutor').values('participant_id')
    campers=items.exclude(participant_id__in=tutor_ids)
    allocations=HouseAllocation.objects.filter(edition=edition,house__edition=edition,status='allocated',participant_id__in=campers.values('participant_id'))
    # Capacity is a current snapshot; date filters select allocation events only.
    allocations=period(allocations,'allocated_at',selected)
    houses=House.objects.filter(edition=edition)
    if selected['status']: houses=houses.filter(status=selected['status'])
    if selected['q']: houses=houses.filter(name__icontains=selected['q'])
    allocations=allocations.filter(house_id__in=houses.values('pk'))
    occupancy=HouseAllocation.objects.filter(house_id=OuterRef('pk'),edition=edition,status='allocated').values('house_id').annotate(n=Count('participant_id',distinct=True)).values('n')
    houses=houses.annotate(occupancy=Subquery(occupancy))
    rows=[]
    for house in houses.order_by('name').values('name','capacity','status','occupancy'):
        occupied=house['occupancy'] or 0
        rows.append(dict(label=house['name'],status=house['status'],value=occupied,capacity=house['capacity'],
            available=None if house['capacity'] is None else max(0,house['capacity']-occupied),
            over_capacity=None if house['capacity'] is None else occupied>house['capacity']))
    eligible=trusted_paid_orders(RegistrationOrder.objects.filter(edition=edition,pk__in=campers.values('order_id')))
    unassigned=campers.filter(order_id__in=eligible).exclude(participant_id__in=HouseAllocation.objects.filter(edition=edition,status='allocated').values('participant_id')).values('participant_id').distinct().count()
    jobs=HousingJob.objects.filter(edition=edition,participant_id__in=campers.values('participant_id'))
    all_capacities_known=bool(rows) and all(row['capacity'] is not None for row in rows)
    return dict(available=True,metrics=[metric('Assigned campers in allocation window',allocations.values('participant_id').distinct().count()),
        metric('Recorded capacity in selected houses',sum(row['capacity'] for row in rows) if all_capacities_known else None),
        metric('Current occupancy in selected houses',sum(row['value'] for row in rows)),
        metric('Available capacity in selected houses',sum(row['available'] for row in rows) if all_capacities_known else None),
        metric('Unassigned payment-evidenced campers',unassigned,'Housing-policy clearance is not inferred.'),
        metric('Fully housing-eligible unassigned',None,'No persisted comprehensive housing-eligibility certificate.'),
        metric('Housing cases held/failed',jobs.filter(state__in=('held','failed')).count()),
        metric('Tutor allocation exceptions',HouseAllocation.objects.filter(edition=edition,status='allocated',participant_id__in=tutor_ids).count())],
        series={'Allocated categories':grouped(campers.filter(participant_id__in=allocations.values('participant_id')),'category_name_snapshot','participant_id'),
            'Housing queue':grouped(jobs,'state')},rows=rows,
        notes=['House capacity/occupancy is current, edition-wide within selected houses; category/date filters scope the allocation count, not shared capacity.',
            'Room-level inventory is not configured. Missing capacity is unknown, not zero. Tutors remain excluded; any existing tutor allocation is an exception, not an entitlement.'])


def movement_findings(arrived, events):
    state='inside' if arrived else 'unknown';issues=0
    for event in events:
        if event['kind']=='departure':
            if state!='inside': issues+=1
            state='outside'
        else:
            if state!='outside': issues+=1
            state='inside'
    return state,issues


def attendance(edition, selected, actor):
    from dic_movement.models import Movement
    if not storage(CampCheckIn,Movement): return unavailable('Arrival/movement schema awaits approved application. No attendance is inferred.')
    participants=scoped_items(edition,selected,registration_dates=False).values('participant_id')
    arrivals=CampCheckIn.objects.filter(edition=edition,participant_id__in=participants)
    moves=Movement.objects.filter(edition=edition,participant_id__in=participants)
    window_arrivals=period(arrivals,'checked_in_at',selected);window_moves=period(moves,'recorded_at',selected)
    # Presence uses the last event as of date_to, not just events inside the window.
    asof={**selected,'date_from':''}
    past_arrivals=period(arrivals,'checked_in_at',asof)
    past_moves=period(moves,'recorded_at',asof)
    last_kind=past_moves.filter(participant_id=OuterRef('participant_id')).order_by('-sequence').values('kind')[:1]
    departed=past_arrivals.annotate(last_kind=Subquery(last_kind)).filter(last_kind='departure').count()
    arrived=past_arrivals.count();registered=RegistrationOrderItem.objects.filter(order__edition=edition,participant_id__in=participants).values('participant_id').distinct().count()
    rows=[];pagination=None
    if actor.has_perm('dic.view_participant'):
        # Bounded event drill-down, no reason, authorization reference or QR token.
        from django.db.models import Value, CharField
        a=window_arrivals.annotate(kind=Value('arrival',output_field=CharField()),stamp=F('checked_in_at')).values_list('participant_id','kind','stamp')
        m=window_moves.annotate(stamp=F('recorded_at')).values_list('participant_id','kind','stamp')
        if selected['q']:
            a=a.filter(participant__id__icontains=selected['q']);m=m.filter(participant__id__icontains=selected['q'])
        if selected['status']=='arrival': events=a.order_by('stamp')
        elif selected['status']: events=m.filter(kind=selected['status']).order_by('stamp')
        else: events=a.order_by().union(m.order_by(),all=True)
        events,pagination=query_page(events,selected,{'date':'stamp','label':'participant_id','value':'stamp','status':'kind'},'stamp')
        for participant,kind,stamp in events:
            rows.append(dict(label=str(participant),status=kind,date=stamp.astimezone(TZ).isoformat(),value=1))
    issues=0;open_departures=0
    # Stream in participant/sequence order; only one person's state is retained.
    arrival_ids=set(past_arrivals.values_list('participant_id',flat=True))
    previous=None;events=[]
    for event in past_moves.order_by('participant_id','sequence').values('participant_id','kind').iterator(chunk_size=500):
        if previous is not None and previous!=event['participant_id']:
            state,n=movement_findings(previous in arrival_ids,events);issues+=n;open_departures+=state=='outside';events=[]
        previous=event['participant_id'];events.append(event)
    if previous is not None:
        state,n=movement_findings(previous in arrival_ids,events);issues+=n;open_departures+=state=='outside'
    return dict(available=True,metrics=[metric('Recorded arrivals in window',window_arrivals.count()),
        metric('Recorded departures in window',window_moves.filter(kind='departure').count()),metric('Recorded returns in window',window_moves.filter(kind='return').count()),
        metric('Inside by latest recorded evidence',arrived-departed),metric('Outside by latest recorded evidence',departed),
        metric('No arrival evidence / unknown',max(0,registered-arrived)),metric('Confirmed absent',None,'A missing scan is not proof of absence.'),
        metric('Open departures (no recorded return)',open_departures),metric('Inconsistent transitions',issues)],
        series={'Daily recorded arrivals':trends(window_arrivals,'checked_in_at'),
            'Daily movement scans':trends(window_moves,'recorded_at')},rows=rows,row_pagination=pagination,
        notes=['Arrival is one initial camp check-in, not daily attendance. Presence is inferred from recorded events only, as of the selected end date.',
            'An open departure is not necessarily an error; no daily checkout deadline is invented. Movement details require participant-view permission in addition to movement/check-in access.',
            'UUID search and status filter scope the event drill-down; KPI totals retain the selected date/category population.'])


def registered_cohort_dates(edition):
    # One query, one first registration per participant, not one per booking.
    return [stamp.astimezone(TZ).date() for stamp in RegistrationOrderItem.objects.filter(order__edition=edition)
        .order_by().values('participant_id').annotate(first_created=Min('order__created_at')).values_list('first_created',flat=True)]


def cohort_participation(count, first_dates, day):
    denominator=sum(first<=date.fromisoformat(day) for first in first_dates)
    return denominator,round(count*100/denominator,2) if denominator and count<=denominator else None


def feedback(edition, selected, actor):
    from .feedback_services import require_feedback_storage, feedback_summary
    try: require_feedback_storage()
    except APIException as error:
        if error.status_code!=503: raise
        return unavailable('Phase 5 feedback schema (0027 and 0031) awaits approval; totals are unavailable.')
    groups=feedback_summary(edition,selected['channel'],date_from=selected['date_from'] or None,date_to=selected['date_to'] or None)
    cohort_dates=registered_cohort_dates(edition) if any(not group['suppressed'] and group['channel'] in ('daily','final') for group in groups) else []
    rows=[];series=[];visible_groups=0
    for group in groups:
        if selected['date_from'] and group['day']<selected['date_from']: continue
        if selected['date_to'] and group['day']>selected['date_to']: continue
        label=f"{group['channel']} / v{group['questionnaire_version']} / {group['day']}"
        if selected['q'] and selected['q'].lower() not in label.lower(): continue
        series.append(dict(label=label,value=group['count']))
        if group['suppressed']:
            rows.append(dict(label=label,date=group['day'],status='Below privacy threshold',value=None))
            continue
        visible_groups+=1
        denominator,rate=cohort_participation(group['count'],cohort_dates,group['day']) if group['channel'] in ('daily','final') else (None,None)
        rows.append(dict(label=label,date=group['day'],status='responses',value=group['count'],
            participation_percent=rate,registered_population=denominator,
            denominator='Distinct participants first registered by camp day, including cancelled/pending; not an eligible-population rate'))
        for key,counts in group['distributions'].items():
            total=sum(counts.values());average=round(sum(int(k)*v for k,v in counts.items())/total,2) if total else None
            for rating,text in group['scale']:
                rows.append(dict(label=label+' / '+group['questions']['ratings'][key],date=group['day'],status=text,
                    value=counts[str(rating)],average=average,scale_max=len(group['scale'])))
        if 'recommendation' in group:
            for choice,n in group['recommendation'].items(): rows.append(dict(label=label+' / Recommend',date=group['day'],status=choice,value=n))
    return dict(available=True,metrics=[metric('Visible reporting groups',visible_groups),
        metric('Eligible-population participation rate',None,'Historical eligible participant-day denominators are not persisted. Tables report the explicit registered-cohort rate instead.')],
        series={'Responses by channel, version and camp day':series},rows=rows,
        notes=['Three-point and five-point results remain separate; averages use only answers to the same question/version.',
            'Anonymous feedback cannot be filtered by camper/category or linked back to a child. Suppressed counts remain unavailable, not zero.',
            'Participation uses distinct participants first registered by that camp day, including pending/cancelled registrations and tutors. It is not an eligibility or attendance measure; rates above 100% are withheld for review.',
            'Authorized comments remain in the existing audited Feedback review; no comments or identities are included in these exports.'])


def welfare(edition, selected, actor):
    from .feedback_services import require_feedback_storage
    try: require_feedback_storage()
    except APIException as error:
        if error.status_code!=503: raise
        return unavailable('Phase 5 welfare schema (0027 and 0031) awaits approval; case counts are unavailable.')
    cases=period(WelfareReport.objects.filter(edition=edition),'created_at',selected)
    for key,field in (('status','status'),('concern_category','category'),('urgency','urgency')):
        if selected[key]: cases=cases.filter(**{field:selected[key]})
    if selected['q']: raise ValidationError('Free-text search is not supported for confidential welfare statistics. Use the authorized case-management interface.')
    statuses=grouped(cases,'status');categories=grouped(cases,'category');urgency=grouped(cases,'urgency')
    events=WelfareEvent.objects.filter(report_id__in=cases.values('pk'),kind='updated',changes__input__status__in=('resolved','closed'))
    events=period(events,'created_at',selected)
    resolution=[dict(label=str(row['day']),value=row['total']) for row in events.order_by()
        .annotate(day=TruncDate('created_at',tzinfo=TZ)).values('day').annotate(total=Count('report_id',distinct=True)).order_by('day')]
    return dict(available=True,metrics=[metric('Complaints',cases.count()),
        metric('Outstanding cases',cases.filter(status__in=('new','review')).count()),
        metric('Assigned cases',cases.filter(assigned_to__isnull=False).count()),metric('Unassigned cases',cases.filter(assigned_to__isnull=True).count())],
        series={'Case status':statuses,'Complaint categories':categories,'Urgency':urgency,'Resolved/closed case events by day':resolution},
        rows=[dict(label=title+' / '+row['label'],status=row['label'],value=row['value'])
            for title,group in (('Status',statuses),('Category',categories),('Urgency',urgency)) for row in group],
        notes=['Requires explicit welfare-view permission, even for aggregates. No camper identities, descriptions, notes, officer identities or case histories are returned.',
            'Date filters select cases created in the window; resolution trends count distinct cases with recorded resolved/closed updates in that window. Reopened cases may appear again on later days.'])


def report(edition, selected, actor, domain):
    require_report(actor,domain)
    if domain=='academic': return unavailable('No persisted teaching-class assignment model exists. Registration categories and houses are not academic classes. Phase 4 remains postponed.')
    handlers={'overview':registration,'registration':registration,'finance':finance,'accommodation':accommodation,
        'attendance':attendance,'feedback':feedback,'welfare':welfare}
    return handlers[domain](edition,selected,actor)


def page_result(data, selected, exporting=False):
    pagination=data.get('row_pagination')
    data={key:value for key,value in data.items() if key!='row_pagination'}
    if pagination is not None:
        result={key:value for key,value in data.items() if key!='row_pagination'}
        result.update(pagination)
        result['columns']=list(dict.fromkeys(key for row in result['rows'] for key in row))
        return result
    rows=data['rows'];key=selected['sort'].lstrip('-')
    rows=sorted(rows,key=lambda row:(row.get(key) is None,row.get(key) if row.get(key) is not None else ''),reverse=selected['sort'].startswith('-'))
    if exporting and len(rows)>5000: raise ValidationError('Narrow report filters to 5,000 detail rows or fewer.')
    total=len(rows);size=5000 if exporting else 50;page=1 if exporting else selected['page']
    result={**data,'rows':rows[(page-1)*size:page*size], 'count':total,'page':page,'page_size':size}
    result['columns']=list(dict.fromkeys(key for row in rows for key in row))
    return result
