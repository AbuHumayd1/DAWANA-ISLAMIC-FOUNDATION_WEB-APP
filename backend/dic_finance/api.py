import csv
import io
from datetime import date
from django.core.exceptions import ObjectDoesNotExist, ValidationError as ModelValidationError
from django.db import IntegrityError, connection
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from dic.operations_api import OperationsBaseView, _edition_from_request
from dic.operations_exports import spreadsheet_safe
from .models import Category, Entry, BudgetRevision, Reconciliation
from .services import require, snapshot, command, audit
from dic.models import CampEdition, RegistrationCategory


class FinanceView(OperationsBaseView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require(request.user)
        if request.method=='GET' and request.query_params.get('metadata')=='1': return
        tables = connection.introspection.table_names()
        if any(model._meta.db_table not in tables for model in [Category,Entry,BudgetRevision,Reconciliation]):
            error = APIException('Finance setup is pending an approved migration. No financial totals are available.')
            error.status_code=503
            raise error

    def get(self, request):
        if request.query_params.get('metadata')=='1':
            return Response({'editions':list(CampEdition.objects.order_by('-year').values('id','name'))})
        edition = _edition_from_request(request)
        if not edition: raise ValidationError('Choose a camp edition.')
        if request.query_params.get('receipt'):
            require(request.user,'view_details')
            try: entry=Entry.objects.get(pk=request.query_params['receipt'],edition=edition)
            except (ObjectDoesNotExist,ValueError,ModelValidationError): raise ValidationError('Receipt not found in this edition.')
            if not entry.receipt: raise ValidationError('No receipt is attached.')
            audit(request.user,'receipt_download',entry,edition=edition.pk)
            response=HttpResponse(bytes(entry.receipt),content_type='application/octet-stream')
            extension={'application/pdf':'pdf','image/png':'png','image/jpeg':'jpg'}.get(entry.receipt_type,'bin')
            response['Content-Disposition']=f'attachment; filename="finance-receipt-{entry.pk}.{extension}"'
            response['X-Content-Type-Options']='nosniff'
            return response
        filters = {key:request.query_params.get(key,'').strip() for key in ['date_from','date_to','category','finance_category','status','payment_status','q']}
        try:
            for key in ['date_from','date_to']:
                if filters[key]: date.fromisoformat(filters[key])
            for key in ['category','finance_category']:
                if filters[key] and int(filters[key])<=0: raise ValueError
            if filters['date_from'] and filters['date_to'] and filters['date_from']>filters['date_to']: raise ValueError
        except (ValueError,TypeError): raise ValidationError('Use valid dates, category IDs and an ordered date range.')
        detailed = request.user.has_perm('dic_finance.can_view_details_finance')
        report = request.query_params.get('export','')
        if report:
            require(request.user,'export'); require(request.user,'view_details')
        output=request.query_params.get('output','csv')
        if output not in ('csv','print'): raise ValidationError('Choose CSV or print output.')
        data = snapshot(edition,filters)
        data['registration_categories']=list(RegistrationCategory.objects.filter(edition=edition).values('id','name'))
        if report:
            choices = {'registration':data['payments'],'reconciliation':data['payments'],
                'income':[r for r in data['entries'] if r['kind']=='income'],
                'expenses':[r for r in data['entries'] if r['kind']=='expense'],
                'budgets':data['budgets'],'summary':[data['summary']]}
            if report not in choices: raise ValidationError('Choose a supported Finance CSV report.')
            rows = choices[report]
            if len(rows)>5000: raise ValidationError('Narrow your filters to 5,000 rows or fewer.')
            headers = list(rows[0]) if rows else ['No matching records']
            stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(headers)
            for row in rows: writer.writerow([spreadsheet_safe(row.get(key,'')) for key in headers])
            audit(request.user,'export',edition,report=report,filters=filters,count=len(rows))
            if output=='print':
                return HttpResponse(render_to_string('dic/finance_report.html',dict(edition=edition,
                    title=report,headers=headers,rows=[[row.get(key,'') for key in headers] for row in rows],
                    filters=filters,semantics='NGN kobo. Budgets and approved commitments are not cash. Net position is recorded activity, not bank settlement or available operating balance.')),
                    content_type='text/html; charset=utf-8')
            response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
            response['Content-Disposition']=f'attachment; filename="dic-finance-{edition.pk}-{report}.csv"'
            return response
        data.update(edition={'id':edition.pk,'name':edition.name}, filters=filters,
            permissions={key:request.user.has_perm(f'dic_finance.can_{key}_finance') for key in
                ['view_details','record_income','submit_expense','approve','confirm_payment','manage_budget','reconcile','export']},
            semantics='NGN kobo. Registration: verified charges less documented refunds/reversals, not bank settlement. Budget is edition-wide; transaction filters affect cash figures only. Registration category filters select whole matching bookings, not apportioned category revenue. Status/search/date filters affect their respective transaction lists.')
        if not detailed:
            for key in ['payments','entries','budgets','budget_history']: data[key]=[]
        else:
            # Bounded paginated transaction lists; summary/export share the full calculation.
            try: page=max(1,int(request.query_params.get('page','1')))
            except ValueError: raise ValidationError('Page must be an integer.')
            data['counts']={key:len(data[key]) for key in ['payments','entries','budget_history']}
            for key in ['payments','entries','budget_history']: data[key]=data[key][(page-1)*50:page*50]
            data['page']=page
        return Response(data)

    def post(self, request):
        edition = _edition_from_request(request)
        if not edition: raise ValidationError('Choose a camp edition.')
        try: result=command(edition,request.user,request.data)
        except ObjectDoesNotExist: raise ValidationError('Record/category not found in the selected edition.')
        except IntegrityError: raise ValidationError('This reference or category already exists. Refresh; do not submit a duplicate.')
        except (ValueError,TypeError,ModelValidationError): raise ValidationError('Check the submitted identifiers, dates and amounts.')
        return Response({'id':str(result.pk),'status':getattr(result,'status','recorded')},status=201)
