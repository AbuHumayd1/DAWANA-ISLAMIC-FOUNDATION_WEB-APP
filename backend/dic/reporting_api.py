"""Unified reporting projection; business records are never modified."""
import csv
import io
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .operations_api import OperationsBaseView
from .operations_exports import spreadsheet_safe
from .models import CampEdition, RegistrationCategory, DICAdminAuditEvent
from . import reporting_services as services


def export_rows(data):
    """The same authorized/filtered payload drives screen, CSV and print."""
    columns=['section','label','date','status','value','unit']
    rows=[]
    for metric in data['metrics']:
        rows.append(dict(section='Summary',label=metric['label'],value=metric['value'],unit=metric['unit']))
    for title,points in data['series'].items():
        for point in points: rows.append(dict(section=title,**point))
    for row in data['rows']:
        rows.append(dict(section='Details',**row))
        for key in row:
            if key not in columns: columns.append(key)
    values = [[row.get(key,'') if row.get(key,'') is not None else 'Unavailable / privacy threshold' for key in columns] for row in rows]
    # Keep stable field keys inside the API; exported headings are for readers.
    headings = {'label': 'Description', 'value': 'Total', 'unit': 'Unit', 'id': 'Reference'}
    return [headings.get(key, key.replace('_', ' ').capitalize()) for key in columns], values


class ReportingView(OperationsBaseView):
    def get(self,request):
        domain=request.query_params.get('domain','overview')
        services.require_report(request.user,domain)
        if request.query_params.get('metadata')=='1':
            return Response(dict(domains=services.capabilities(request.user),
                editions=list(CampEdition.objects.order_by('-year','-pk').values('id','name')),
                timezone='Africa/Lagos'))
        try:
            edition_id=int(request.query_params.get('edition',''))
            if edition_id<=0: raise ValueError
        except (ValueError,TypeError): raise ValidationError('Choose an explicit camp edition.')
        edition=CampEdition.objects.filter(pk=edition_id).first()
        if not edition: raise ValidationError('Choose an existing camp edition.')
        selected=services.filters(request.query_params,domain)
        if selected['category'] and not RegistrationCategory.objects.filter(pk=selected['category'],edition=edition).exists():
            raise ValidationError('Category is not in the selected edition.')
        exporting=request.query_params.get('export','')
        if exporting and exporting not in ('csv','print'): raise ValidationError('Choose CSV or print export.')
        if exporting and domain=='finance' and not all(request.user.has_perm('dic_finance.can_'+permission+'_finance') for permission in ('export','view_details')):
            raise PermissionDenied('Finance detail and export permissions are required.')
        selected['_exporting']=bool(exporting)
        data=services.page_result(services.report(edition,selected,request.user,domain),selected,exporting=bool(exporting))
        data.update(domain=domain,title=services.DOMAINS[domain][0],edition={'id':edition.pk,'name':edition.name},
            filters={key:value for key,value in selected.items() if key!='q' and not key.startswith('_')},
            categories=list(RegistrationCategory.objects.filter(edition=edition).order_by('name').values('id','name')),
            generated_at=timezone.now().astimezone(services.TZ).isoformat(),timezone='Africa/Lagos')
        # Audit access, never raw search strings, report contents or personal data.
        DICAdminAuditEvent.objects.create(actor=request.user,
            action='reporting_exported' if exporting else 'reporting_viewed',
            target_type='CampEdition',target_id=str(edition.pk),
            details={'domain':domain,'format':exporting or 'screen','date_from':selected['date_from'],'date_to':selected['date_to']})
        if exporting:
            headers,rows=export_rows(data)
            if len(rows)>10000: raise ValidationError('Narrow filters to 10,000 exported summary/detail rows or fewer.')
            if exporting=='csv':
                stream=io.StringIO();writer=csv.writer(stream);writer.writerow(headers)
                writer.writerows([[spreadsheet_safe(value) for value in row] for row in rows])
                response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
                response['Content-Disposition']=f'attachment; filename="dic-{edition.pk}-{domain}.csv"'
                return response
            return HttpResponse(render_to_string('dic/reporting.html',dict(data=data,headers=headers,rows=rows)),content_type='text/html; charset=utf-8')
        data['can_export']=domain!='finance' or all(request.user.has_perm('dic_finance.can_'+permission+'_finance') for permission in ('export','view_details'))
        data['drilldowns']=drilldowns(request.user,domain,edition.pk)
        return Response(data)


def drilldowns(actor,domain,edition):
    routes={'registration':('dic.view_registrationorder','registrations'),
        'finance':('dic_finance.can_view_details_finance','finance'),
        'accommodation':('dic.view_houseallocation','houses'),
        'attendance':('dic.view_participant','participants'),
        'feedback':('dic.can_read_dic_feedback_details','feedback'),
        'welfare':('dic.can_view_dic_welfare','welfare')}
    if domain not in routes or not actor.has_perm(routes[domain][0]): return []
    return [dict(label='Open authorized '+routes[domain][1]+' review',url=f'/dic/operations/{routes[domain][1]}?edition={edition}')]
