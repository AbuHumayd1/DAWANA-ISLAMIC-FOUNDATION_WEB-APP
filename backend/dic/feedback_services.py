import hashlib
import hmac
import json
from collections import defaultdict
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from .models import (AnonymousCamperResponse, CamperFeedbackReceipt, IdentifiedFeedback,
    LecturerFeedbackAccess, WelfareReport, WelfareEvent, RegistrationOrderItem, LecturerAppearance)
from .campsite_api import require_campsite_staff
from .participant_api import authorized_grant, scoped_orders
from .feedback_schema import QUESTIONS, CATEGORIES, STATUSES, questionnaire, RATINGS, LEGACY_RATINGS, CAMP_TIMEZONE


def camp_today():
    return timezone.localdate(timezone=ZoneInfo(CAMP_TIMEZONE))


def require_feedback_staff(user, permission):
    require_campsite_staff(user)
    if not user.has_perm('dic.'+permission):
        raise PermissionDenied('Your account does not have permission for this feedback or welfare action.')


def require_feedback_storage():
    tables = connection.introspection.table_names()
    if any(model._meta.db_table not in tables for model in (AnonymousCamperResponse, CamperFeedbackReceipt,
            IdentifiedFeedback, LecturerFeedbackAccess, WelfareReport, WelfareEvent)):
        error = APIException('Feedback and Welfare setup is pending. Schema and privacy approval are required before activation.')
        error.status_code = 503
        raise error
    # Fail closed on partially applied Phase 5 schema as well as missing tables.
    with connection.cursor() as cursor:
        for model, required in ((AnonymousCamperResponse, {'questionnaire_version'}),
                (IdentifiedFeedback, {'questionnaire_version'}),
                (WelfareReport, {'affected_participant_id', 'urgency', 'preferred_contact'})):
            columns = {column.name for column in connection.introspection.get_table_description(cursor, model._meta.db_table)}
            if not required <= columns:
                error = APIException('Phase 5 schema approval and setup are pending.')
                error.status_code = 503
                raise error


class ResponseInput(serializers.Serializer):
    channel = serializers.ChoiceField(choices=tuple(QUESTIONS))
    day = serializers.DateField()
    ratings = serializers.DictField(child=serializers.IntegerField(min_value=1,max_value=5))
    answers = serializers.DictField(child=serializers.CharField(max_length=1000,allow_blank=True), default=dict)
    recommend = serializers.BooleanField(required=False)


def validate_response(payload, edition, allowed, tutor=False):
    form = ResponseInput(data=payload); form.is_valid(raise_exception=True)
    data = form.validated_data
    kind = data['channel']; spec = questionnaire(kind, tutor=tutor)
    if kind not in allowed:
        raise PermissionDenied('This feedback channel is not available through this account.')
    required_ratings = set(spec['ratings']) - set(spec.get('optional_ratings', ()))
    if (not required_ratings <= set(data['ratings']) or set(data['ratings']) - set(spec['ratings'])
            or set(data['answers']) - set(spec['comments'])):
        raise ValidationError('Answer the displayed rating questions only; do not send identity fields.')
    today = camp_today()
    if not edition.camp_start_date <= data['day'] <= edition.camp_end_date or data['day'] > today:
        raise ValidationError('Choose a camp day that has already started.')
    if kind == 'final':
        if data['day'] != edition.camp_end_date or today < edition.camp_end_date or 'recommend' not in data:
            raise ValidationError('Final evaluation is available on the final camp day; answer the recommendation question.')
        data['answers']['recommend'] = data['recommend']
    elif kind == 'daily' and data['day'] != today:
        raise ValidationError('Daily feedback is available only on that camp date.')
    elif 'recommend' in data:
        raise ValidationError('Recommendation is a final-evaluation question only.')
    return data


def portal_item(request, item_id, lock=False):
    grant = authorized_grant(request, lock=lock)
    orders = scoped_orders(grant)
    item = RegistrationOrderItem.objects.select_related('order__edition','order__primary_registrant','participant').filter(
        pk=item_id, order_id__in=[order.pk for order in orders]).first()
    if not item:
        raise PermissionDenied('Choose a participant in your verified booking session.')
    return item


def receipt_digest(participant_id, edition_id, day, channel):
    secret = settings.DIC_FEEDBACK_PRIVACY_KEY
    if len(secret) < 32:
        error = APIException('Anonymous feedback privacy setup is pending. Ask an organiser for assistance.')
        error.status_code = 503
        raise error
    message = json.dumps(['dic-feedback-v1',str(participant_id),edition_id,str(day),channel],separators=(',',':'))
    return hmac.new(secret.encode(),message.encode(),hashlib.sha256).hexdigest()


@transaction.atomic
def submit_camper(request, item_id, payload):
    item = portal_item(request,item_id,lock=True)
    data = validate_response(payload,item.order.edition,('daily','final'),
        tutor=getattr(item.order, 'registration_basis', '') == 'tutor')
    # Final uniqueness is per edition, even if officials later correct its end
    # date. Preserve historical date-based receipts without linking responses.
    if data['channel'] == 'final':
        legacy_days = AnonymousCamperResponse.objects.filter(edition=item.order.edition,
            channel='final',questionnaire_version=1).values_list('day',flat=True).distinct()
        legacy_digests = [receipt_digest(item.participant_id,item.order.edition_id,day,'final') for day in legacy_days]
        if legacy_digests and CamperFeedbackReceipt.objects.filter(digest__in=legacy_digests).exists():
            return False
    digest = receipt_digest(item.participant_id,item.order.edition_id,
        'final' if data['channel']=='final' else data['day'],data['channel'])
    _, created = CamperFeedbackReceipt.objects.get_or_create(digest=digest)
    if created:
        AnonymousCamperResponse.objects.create(edition=item.order.edition,day=data['day'],channel=data['channel'],
            ratings=data['ratings'],answers=data['answers'])
    # No response identifier, participant identifier or precise submission time.
    return created


@transaction.atomic
def submit_identified(edition, actor, payload):
    kind = payload.get('channel') if isinstance(payload,dict) else None
    if kind not in ('staff','lecturer'):
        raise ValidationError('Choose staff or lecturer feedback.')
    require_feedback_staff(actor,'can_submit_dic_'+kind+'_feedback')
    data = validate_response(payload,edition,(kind,))
    lecturer = None
    if kind == 'lecturer':
        access = LecturerFeedbackAccess.objects.filter(edition=edition,user=actor,enabled=True).first()
        appearance = LecturerAppearance.objects.filter(edition=edition,lecturer_id=access.lecturer_id).first() if access else None
        if not appearance or not appearance.verified:
            raise PermissionDenied('An administrator must explicitly link your account to a confirmed lecturer for this edition.')
        lecturer = access.lecturer
    _, created = IdentifiedFeedback.objects.get_or_create(edition=edition,author=actor,channel=kind,day=data['day'],
        defaults=dict(lecturer=lecturer,ratings=data['ratings'],answers=data['answers']))
    return created


class WelfareInput(serializers.Serializer):
    urgency = serializers.ChoiceField(choices=('normal','urgent'), default='normal')
    preferred_contact = serializers.ChoiceField(choices=('none','email','in_person'), default='none')
    category = serializers.ChoiceField(choices=tuple(CATEGORIES))
    description = serializers.CharField(max_length=5000)
    assistance_person = serializers.CharField(max_length=200,allow_blank=True,default='')
    request_id = serializers.UUIDField()


@transaction.atomic
def create_welfare(edition, payload, *, user=None, registrant=None, participant=None):
    if (user is None)==(registrant is None):
        raise ValidationError('Exactly one verified reporter is required.')
    if user is not None:
        require_feedback_staff(user,'can_submit_dic_welfare')
    if registrant is not None and participant is None:
        raise ValidationError('Choose the affected camper in your authorized booking.')
    form = WelfareInput(data=payload); form.is_valid(raise_exception=True)
    data = form.validated_data
    values = dict(edition=edition,reporter_user=user,reporter_registrant=registrant,
        affected_participant=participant, urgency=data['urgency'], preferred_contact=data['preferred_contact'],
        category=data['category'],description=data['description'],assistance_person=data['assistance_person'])
    report, created = WelfareReport.objects.get_or_create(request_id=data['request_id'],defaults=values)
    if not created:
        for key,value in values.items():
            actual=getattr(report,key+'_id') if key in ('edition','reporter_user','reporter_registrant','affected_participant') else getattr(report,key)
            expected=(value.pk if value else None) if key in ('edition','reporter_user','reporter_registrant','affected_participant') else value
            if actual!=expected:
                raise ValidationError('This submission reference has already been used. Refresh the form.')
    if created:
        WelfareEvent.objects.create(report=report,actor=user,kind='created',changes={'status':'new'})
    return report, created


class WelfareUpdateInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=tuple(STATUSES))
    assigned_to = serializers.IntegerField(min_value=1,allow_null=True)
    note = serializers.CharField(max_length=3000)
    version = serializers.IntegerField(min_value=1)
    request_id = serializers.UUIDField()


def welfare_officers():
    from django.contrib.auth import get_user_model
    return [user for user in get_user_model().objects.filter(is_active=True,is_staff=True)
        if user.has_perm('dic.can_view_dic_operations') and user.has_perm('dic.can_view_dic_welfare') and user.has_perm('dic.can_manage_dic_welfare')]


@transaction.atomic
def update_welfare(edition, report_id, actor, payload):
    require_feedback_staff(actor,'can_view_dic_welfare')
    require_feedback_staff(actor,'can_manage_dic_welfare')
    form = WelfareUpdateInput(data=payload); form.is_valid(raise_exception=True)
    data = form.validated_data
    report = WelfareReport.objects.select_for_update().filter(pk=report_id,edition=edition).first()
    if not report:
        raise ValidationError('Report not found in this camp edition.')
    signature = dict(status=data['status'],assigned_to=data['assigned_to'],version=data['version'])
    event = WelfareEvent.objects.filter(request_id=data['request_id']).first()
    if event:
        if event.report_id==report.pk and event.actor_id==actor.pk and event.note==data['note'] and event.changes.get('input')==signature:
            return report, False
        raise ValidationError('This update reference was already used.')
    if report.version != data['version']:
        raise ValidationError('This report changed. Refresh it before saving your update.')
    officer = None
    if data['assigned_to'] is not None:
        officer = next((user for user in welfare_officers() if user.pk==data['assigned_to']),None)
        if not officer:
            raise ValidationError('Choose an active authorised welfare officer.')
    changes = dict(input=signature,previous_status=report.status,previous_officer=report.assigned_to_id)
    report.status, report.assigned_to = data['status'], officer
    report.version += 1
    report.save(update_fields=('status','assigned_to','version'))
    WelfareEvent.objects.create(report=report,actor=actor,kind='updated',note=data['note'],changes=changes,request_id=data['request_id'])
    return report, True


def feedback_summary(edition, channel='', day=None, details=False, date_from=None, date_to=None):
    groups = defaultdict(list)
    # Deliberately never query welfare or duplicate receipts from analytics.
    for model in (AnonymousCamperResponse,IdentifiedFeedback):
        query = model.objects.filter(edition=edition)
        if channel: query = query.filter(channel=channel)
        if day: query = query.filter(day=day)
        if date_from: query = query.filter(day__gte=date_from)
        if date_to: query = query.filter(day__lte=date_to)
        for row in query:
            groups[(row.channel,row.day,getattr(row, 'questionnaire_version', 1))].append(row)
    result = []
    for (kind,date,version),rows in sorted(groups.items()):
        suppressed = kind in ('daily','final') and len(rows)<5
        questions = questionnaire(kind, version=version)
        scale = LEGACY_RATINGS if version == 1 else RATINGS
        distributions = {key:{str(rating):sum(row.ratings.get(key)==rating for row in rows) for rating,_ in scale}
            for key in questions['ratings']
            if kind not in ('daily','final') or sum(key in row.ratings for row in rows) >= 5}
        item = dict(channel=kind,day=date.isoformat(),count=None if suppressed else len(rows),suppressed=suppressed,
            questionnaire_version=version, questions=questions, scale=scale,
            distributions={} if suppressed else distributions)
        if kind=='final' and not suppressed:
            item['recommendation']={'yes':sum(row.answers.get('recommend') is True for row in rows),
                'no':sum(row.answers.get('recommend') is False for row in rows)}
        if details and not suppressed:
            item['responses'] = [dict(answers=row.answers,
                **({'author':row.author.get_full_name() or row.author.get_username(), 'lecturer':row.lecturer.name if row.lecturer_id else None} if kind in ('staff','lecturer') else {})) for row in rows]
        result.append(item)
    return result
