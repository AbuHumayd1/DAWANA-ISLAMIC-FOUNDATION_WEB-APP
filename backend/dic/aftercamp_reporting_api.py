"""Camp-wide, permission-scoped consolidated report for Operations."""
from django.http import HttpResponse
from django.db import transaction
from django.utils import timezone
from django.template.loader import render_to_string
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response

from .operations_api import OperationsBaseView
from .models import CampEdition, DICAdminAuditEvent, AftercampAssessment
from .aftercamp_models import ASSESSMENT_TOPICS
from .aftercamp_evidence import editorial_drafts
from . import reporting_services
from .aftercamp_reports import build, export_word


class AfterCampReportView(OperationsBaseView):
    def get(self, request):
        reporting_services.require_report(request.user, 'overview')
        try:
            edition_id = int(request.query_params.get('edition', ''))
            if edition_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError('Choose an explicit camp edition.')
        edition = CampEdition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise ValidationError('Choose an existing camp edition.')

        fmt = request.query_params.get('export', '')
        if fmt not in ('', 'docx', 'print'):
            raise ValidationError('Choose Word or print export.')
        payload = build(edition, request.user, for_download=bool(fmt))
        if not fmt and request.user.is_superuser:
            payload['editorial_drafts'] = editorial_drafts(edition, request.user)
        DICAdminAuditEvent.objects.create(
            actor=request.user, action='reporting_exported' if fmt else 'reporting_viewed',
            target_type='CampEdition', target_id=str(edition.pk),
            details={'domain': 'aftercamp', 'format': fmt or 'screen'},
        )
        if fmt == 'docx':
            response = HttpResponse(export_word(payload),
                                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            response['Content-Disposition'] = (
                f'attachment; filename="dic-{edition.year}-camp-report.docx"')
            return response
        if fmt == 'print':
            return HttpResponse(render_to_string('dic/aftercamp_reporting.html', {'report': payload}),
                                content_type='text/html; charset=utf-8')
        return Response(payload)

    def post(self, request):
        reporting_services.require_report(request.user, 'overview')
        if not request.user.is_superuser:
            raise PermissionDenied('Only an authorized camp reporting administrator may approve committee assessments.')
        try:
            edition_id = int(request.data.get('edition', 0))
        except (ValueError, TypeError):
            raise ValidationError({'edition': 'Choose an explicit camp edition.'})
        edition = CampEdition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise ValidationError({'edition': 'Choose an existing edition.'})
        topic = str(request.data.get('topic', '')).strip()
        action = str(request.data.get('action', 'save')).strip()
        if topic not in dict(ASSESSMENT_TOPICS):
            raise ValidationError({'topic': 'Choose a supported committee assessment topic.'})
        if action not in ('save', 'approve', 'reopen'):
            raise ValidationError({'action': 'Choose save, approve or reopen.'})
        limits = {'findings':10000,'challenges':6000,'recommendations':6000,'evidence_reference':1500}
        supplied = {}
        if action == 'save':
            for key, limit in limits.items():
                value = request.data.get(key, '')
                if not isinstance(value, str) or len(value) > limit:
                    raise ValidationError({key: f'Use text of at most {limit} characters.'})
                supplied[key] = value.strip()
        with transaction.atomic():
            record, _ = AftercampAssessment.objects.select_for_update().get_or_create(
                edition=edition, topic=topic, defaults={'authored_by':request.user})
            if action == 'save':
                if record.status == 'approved':
                    raise ValidationError('Reopen the approved assessment before making a revision.')
                for key, value in supplied.items():
                    setattr(record,key,value)
                record.authored_by = request.user
                record.save()
            elif action == 'approve':
                if not record.findings or not record.evidence_reference:
                    raise ValidationError('Findings and a traceable evidence reference are required for approval.')
                if record.status == 'approved':
                    raise ValidationError('This assessment is already approved.')
                record.status = 'approved'
                record.approved_by = request.user
                record.approved_at = timezone.now()
                record.save(update_fields=['status','approved_by','approved_at','updated_at'])
            else:
                if record.status != 'approved':
                    raise ValidationError('Only an approved assessment can be reopened.')
                record.status = 'draft'
                record.approved_by = None
                record.approved_at = None
                record.save(update_fields=['status','approved_by','approved_at','updated_at'])
            DICAdminAuditEvent.objects.create(
                actor=request.user, action='aftercamp_assessment_' + action,
                target_type='AftercampAssessment', target_id=str(record.pk),
                details={'edition':edition.pk,'topic':topic,'status':record.status})
        return Response({'topic':topic,'status':record.status})
