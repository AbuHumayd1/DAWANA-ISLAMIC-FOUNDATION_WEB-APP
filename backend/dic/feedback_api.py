import csv
import io
from datetime import date
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import CampEdition, RegistrationOrderItem, WelfareReport, WelfareEvent, DICAdminAuditEvent
from .operations_api import OperationsBaseView, _edition_from_request
from .operations_exports import spreadsheet_safe
from .participant_api import PortalView, authorized_grant, scoped_orders
from .feedback_schema import QUESTIONS, RATINGS, CATEGORIES, STATUSES, PRIVACY_NOTICE, URGENT_NOTICE, questionnaire
from .feedback_services import (require_feedback_staff,require_feedback_storage,portal_item,submit_camper,
    submit_identified,create_welfare,update_welfare,welfare_officers,feedback_summary,camp_today)


def explicit_edition(request):
    if not request.query_params.get('edition'):
        raise ValidationError('Choose a camp edition.')
    return _edition_from_request(request)


def item_id(payload):
    field = serializers.IntegerField(min_value=1)
    return field.run_validation(payload.get('item_id') if isinstance(payload,dict) else None)


def spec():
    return dict(questions=QUESTIONS,ratings=RATINGS,categories=CATEGORIES,statuses=STATUSES,privacy=PRIVACY_NOTICE,urgent=URGENT_NOTICE)


class CamperFeedbackOptionsView(PortalView):
    def get(self,request):
        grant = authorized_grant(request)
        require_feedback_storage()
        orders = scoped_orders(grant)
        items = RegistrationOrderItem.objects.filter(order_id__in=[row.pk for row in orders]).select_related('participant','order__edition')
        return Response(dict(**spec(),today=str(camp_today()),expires_at=grant.expires_at.isoformat(),items=[dict(id=row.pk,name=row.participant.full_name,edition=row.order.edition_id,
            questions={kind:questionnaire(kind, tutor=row.order.registration_basis=='tutor') for kind in ('daily','final')},
            edition_name=row.order.edition.name,start=str(row.order.edition.camp_start_date),end=str(row.order.edition.camp_end_date)) for row in items]))


class CamperFeedbackSubmitView(PortalView):
    def post(self,request):
        authorized_grant(request)
        require_feedback_storage()
        created = submit_camper(request,item_id(request.data),request.data)
        return Response(dict(accepted=True,duplicate=not created),status=201 if created else 200)


class CamperWelfareSubmitView(PortalView):
    def get(self,request):
        authorized_grant(request)
        require_feedback_storage()
        item = portal_item(request,item_id(request.query_params))
        rows = WelfareReport.objects.filter(edition=item.order.edition,
            reporter_registrant=item.order.primary_registrant,
            affected_participant=item.participant).order_by('-created_at')
        # Explicit allowlist: no officer identity, notes, private events or reporter contacts.
        return Response({'results':[dict(id=str(row.pk),category=row.category,description=row.description,
            urgency=row.urgency,status=row.status,status_label=STATUSES[row.status],
            time=row.created_at.isoformat()) for row in rows]})

    def post(self,request):
        authorized_grant(request)
        require_feedback_storage()
        with transaction.atomic():
            item = portal_item(request,item_id(request.data),lock=True)
            if not item.order.edition.camp_start_date <= camp_today() <= item.order.edition.camp_end_date:
                raise ValidationError('Online complaints can be submitted during camp dates.')
            _,created = create_welfare(item.order.edition,request.data,registrant=item.order.primary_registrant,
                participant=item.participant)
        return Response(dict(accepted=True,duplicate=not created),status=201 if created else 200)


class FeedbackFormOptionsView(OperationsBaseView):
    def get(self,request):
        # Options contain no submitted records or personal identities.
        from .campsite_api import require_campsite_staff
        require_campsite_staff(request.user)
        require_feedback_storage()
        return Response(dict(**spec(),editions=list(CampEdition.objects.order_by('-year').values('id','name','year','camp_start_date','camp_end_date'))))


class IdentifiedFeedbackSubmitView(OperationsBaseView):
    def post(self,request):
        # Authorisation is repeated in the service, including channel/mapping.
        kind=request.data.get('channel') if isinstance(request.data,dict) else None
        if kind not in ('staff','lecturer'): raise ValidationError('Choose staff or lecturer feedback.')
        require_feedback_staff(request.user,'can_submit_dic_'+kind+'_feedback')
        require_feedback_storage()
        created = submit_identified(explicit_edition(request),request.user,request.data)
        return Response(dict(accepted=True,duplicate=not created),status=201 if created else 200)


class FeedbackSummaryView(OperationsBaseView):
    def get(self,request):
        require_feedback_staff(request.user,'can_view_dic_feedback')
        exporting = request.query_params.get('export')
        if exporting:
            require_feedback_staff(request.user,'can_export_dic_reports')
            if exporting not in ('csv','print'): raise ValidationError('Choose CSV or print.')
        require_feedback_storage()
        edition = _edition_from_request(request)
        channel = request.query_params.get('channel','')
        if channel and channel not in QUESTIONS: raise ValidationError('Choose a general feedback channel.')
        day = None
        if request.query_params.get('day'):
            try: day = date.fromisoformat(request.query_params['day'])
            except ValueError as exc: raise ValidationError('Choose a valid camp day.') from exc
            if edition and not edition.camp_start_date <= day <= edition.camp_end_date: raise ValidationError('Day is outside this edition.')
        details = request.query_params.get('details')=='1'
        if details: require_feedback_staff(request.user,'can_read_dic_feedback_details')
        rows = feedback_summary(edition,channel,day,details=details and not exporting) if edition else []
        if exporting:
            DICAdminAuditEvent.objects.create(actor=request.user,action='feedback_summary_exported',target_type='CampEdition',target_id=str(edition.pk) if edition else '',details={'format':exporting})
            if exporting=='print':
                print_rows=[{**row,'distributions':{row['questions']['ratings'][key]:counts for key,counts in row['distributions'].items()}} for row in rows]
                response = HttpResponse(render_to_string('dic/feedback_summary.html',dict(edition=edition,rows=print_rows,generated_at=timezone.now())),content_type='text/html; charset=utf-8')
            else:
                output=io.StringIO(); writer=csv.writer(output)
                writer.writerow(['Camp','Channel','Camp day','Questionnaire version','Response count','Question','Rating','Label','Count'])
                for row in rows:
                    prefix=[spreadsheet_safe(edition.name),row['channel'],row['day'],row['questionnaire_version']]
                    if row['suppressed']: writer.writerow([*prefix,'Below privacy threshold','','','',''])
                    for key,counts in row['distributions'].items():
                        for rating,label in row['scale']:
                            writer.writerow([*prefix,row['count'],row['questions']['ratings'][key],rating,label,counts[str(rating)]])
                    if 'recommendation' in row:
                        for choice,count in row['recommendation'].items():
                            writer.writerow([*prefix,row['count'],'Would recommend','',choice,count])
                response=HttpResponse(output.getvalue(),content_type='text/csv; charset=utf-8'); response['Content-Disposition']='attachment; filename="dic-feedback-summary.csv"'
            response['Cache-Control']='private, no-store'
            return response
        if details:
            DICAdminAuditEvent.objects.create(actor=request.user,action='feedback_details_accessed',target_type='CampEdition',target_id=str(edition.pk) if edition else '',details={})
        return Response(dict(edition=dict(id=edition.pk,name=edition.name) if edition else None,
            editions=list(CampEdition.objects.order_by('-year').values('id','name','year','camp_start_date','camp_end_date')),rows=rows,**spec()))


class WelfareReportsView(OperationsBaseView):
    def get(self,request):
        require_feedback_staff(request.user,'can_view_dic_welfare')
        require_feedback_storage()
        edition=_edition_from_request(request)
        rows=WelfareReport.objects.filter(edition=edition).select_related('assigned_to').order_by('-created_at') if edition else []
        status=request.query_params.get('status','')
        if status:
            if status not in STATUSES: raise ValidationError('Choose a valid status.')
            rows=rows.filter(status=status) if edition else []
        for key,choices in (('category',CATEGORIES),('urgency',('normal','urgent'))):
            value=request.query_params.get(key,'')
            if value:
                if value not in choices: raise ValidationError('Choose a valid complaint filter.')
                rows=rows.filter(**{key:value}) if edition else []
        # No reporter/description/note in list or any general feedback endpoint.
        return Response(dict(edition=dict(id=edition.pk,name=edition.name) if edition else None,
            editions=list(CampEdition.objects.order_by('-year').values('id','name','year')),
            results=[dict(id=str(row.pk),category=row.category,urgency=row.urgency,status=row.status,time=row.created_at.isoformat(),assigned_to=row.assigned_to_id) for row in rows],
            officers=[dict(id=user.pk,name=user.get_full_name() or user.get_username()) for user in welfare_officers()] if request.user.has_perm('dic.can_manage_dic_welfare') else [],**spec()))

    def post(self,request):
        require_feedback_staff(request.user,'can_submit_dic_welfare')
        require_feedback_storage()
        _,created=create_welfare(explicit_edition(request),request.data,user=request.user)
        return Response(dict(accepted=True,duplicate=not created),status=201 if created else 200)


class WelfareReportDetailView(OperationsBaseView):
    def get(self,request,report_id):
        require_feedback_staff(request.user,'can_view_dic_welfare')
        require_feedback_storage()
        # Denied requests must not open a database transaction. Keep the
        # authorised confidential read and its access event atomic together.
        with transaction.atomic():
            report=WelfareReport.objects.filter(pk=report_id,edition=explicit_edition(request)).select_related('reporter_user','reporter_registrant','assigned_to').first()
            if not report: raise ValidationError('Report not found in this edition.')
            WelfareEvent.objects.create(report=report,actor=request.user,kind='viewed')
            reporter=report.reporter_user or report.reporter_registrant
            name=(reporter.get_full_name() or reporter.get_username()) if report.reporter_user_id else reporter.full_name
            return Response(dict(id=str(report.pk),category=report.category,description=report.description,
                urgency=report.urgency,preferred_contact=report.preferred_contact,
                affected_camper=report.affected_participant.full_name if report.affected_participant_id else None,
                reporter=name,assistance_person=report.assistance_person,status=report.status,assigned_to=report.assigned_to_id,
                assigned_name=(report.assigned_to.get_full_name() or report.assigned_to.get_username()) if report.assigned_to_id else None,
                time=report.created_at.isoformat(),version=report.version,
                events=[dict(kind=row.kind,note=row.note,changes=row.changes,time=row.created_at.isoformat(),
                    staff=(row.actor.get_full_name() or row.actor.get_username()) if row.actor_id else 'Verified booking reporter') for row in report.events.select_related('actor').order_by('created_at','pk')]))

    def post(self,request,report_id):
        require_feedback_staff(request.user,'can_view_dic_welfare'); require_feedback_staff(request.user,'can_manage_dic_welfare')
        require_feedback_storage()
        _,changed=update_welfare(explicit_edition(request),report_id,request.user,request.data)
        return Response(dict(saved=True,duplicate=not changed))
