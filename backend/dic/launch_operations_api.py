"""Private, session/CSRF-protected Operations adapters over launch services."""
from django.core.exceptions import ValidationError as ModelValidationError, PermissionDenied as ModelPermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction, connection
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from .operations_api import OperationsBaseView
from .campsite_api import require_campsite_staff
from .models import AcademicClass, AcademicAssignment, CampAnnouncement, CampEdition, Participant, RegistrationOrderItem, DICAdminAuditEvent
from .launch_management import (require_launch_permission, save_academic, save_announcement_draft,
                               publish_announcement, StaleLaunchRecord)


class Conflict(APIException):
    status_code = 409
    default_detail = 'This record changed. Reload before trying again.'


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({api_settings.NON_FIELD_ERRORS_KEY: ['Only the documented fields are accepted.']})
        return super().to_internal_value(data)


class ClassInput(StrictInput):
    name = serializers.CharField(max_length=120)
    active = serializers.BooleanField()
    version = serializers.CharField(required=False, max_length=64)


class AssignmentInput(StrictInput):
    participant = serializers.UUIDField()
    academic_class = serializers.IntegerField(min_value=1)
    assignment = serializers.IntegerField(min_value=1, required=False)
    version = serializers.CharField(required=False, max_length=64)
    reason = serializers.CharField(max_length=500)


class DraftInput(StrictInput):
    title = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=5000)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    version = serializers.CharField(required=False, max_length=64)

    def validate(self, data):
        if data['starts_at'] and data['ends_at'] and data['starts_at'] >= data['ends_at']:
            raise ValidationError('Announcement end must follow its start.')
        return data


class PublicationInput(StrictInput):
    action = serializers.ChoiceField(choices=('publish', 'withdraw'))
    version = serializers.CharField(max_length=64)
    reason = serializers.CharField(max_length=500)


def validated(form, payload):
    serializer = form(data=payload)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def edition_for(request):
    edition_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1).run_validation(request.query_params.get('edition'))
    try:
        return CampEdition.objects.get(pk=edition_id)
    except CampEdition.DoesNotExist:
        raise NotFound('Camp edition unavailable.') from None


def page_of(query, request):
    number = serializers.IntegerField(min_value=1, max_value=100000).run_validation(request.query_params.get('page', 1))
    paginator = Paginator(query, 50)
    if number > paginator.num_pages:
        raise ValidationError('Page unavailable. Return to the first page.')
    page = paginator.page(number)
    return dict(count=paginator.count, page=page.number, pages=paginator.num_pages, results=list(page.object_list))


def call_service(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except StaleLaunchRecord as error:
        raise Conflict(' '.join(error.messages)) from None
    except ModelPermissionDenied:
        raise PermissionDenied('Explicit active staff permission is required.') from None
    except ModelValidationError as error:
        raise ValidationError(getattr(error, 'message_dict', None) or error.messages) from None
    except (AcademicClass.DoesNotExist, AcademicAssignment.DoesNotExist, CampAnnouncement.DoesNotExist):
        raise NotFound('Record unavailable in this edition.') from None
    except IntegrityError:
        raise Conflict('A conflicting record was saved. Reload before trying again.') from None


def require_version(data):
    version = data.pop('version', None)
    if not version:
        raise ValidationError('Reload this record before editing; a version token is required.')
    return version


def require_launch_storage(domain):
    models = (AcademicClass, AcademicAssignment) if domain == 'classes' else (CampAnnouncement,)
    required = {model._meta.db_table for model in (*models, DICAdminAuditEvent)}
    if not required.issubset(connection.introspection.table_names()):
        error = APIException('Camp management schema setup is pending. No changes were made.')
        error.status_code = 503
        raise error


def class_row(row):
    return dict(id=row.pk, name=row.name, active=row.active, version=row.updated_at.isoformat(),
                assigned_count=getattr(row, 'assigned_count', None))


def announcement_row(row):
    now = timezone.now()
    visibility = ('draft' if row.status == 'draft' else 'scheduled' if row.starts_at and row.starts_at > now
                  else 'expired' if row.ends_at and row.ends_at <= now else 'visible')
    return dict(id=row.pk, title=row.title, body=row.body, status=row.status, visibility=visibility,
                audience='edition', starts_at=row.starts_at.isoformat() if row.starts_at else None,
                ends_at=row.ends_at.isoformat() if row.ends_at else None, version=row.updated_at.isoformat())


class LaunchOperationsBase(OperationsBaseView):
    domain = 'classes'

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_campsite_staff(request.user)
        permissions = ('manage_dic_classes',) if self.domain == 'classes' else ('manage_dic_announcements', 'publish_dic_announcements')
        if not any(request.user.has_perm('dic.' + value) for value in permissions):
            raise PermissionDenied('Explicit academic or announcement permission is required.')
        require_launch_storage(self.domain)


class LaunchOptionsView(LaunchOperationsBase):
    def initial(self, request, *args, **kwargs):
        # Options are private to at least one editor; do not require class access
        # from announcement-only publishers.
        OperationsBaseView.initial(self, request, *args, **kwargs)
        require_campsite_staff(request.user)
        if not any(request.user.has_perm('dic.' + value) for value in (
                'manage_dic_classes', 'manage_dic_announcements', 'publish_dic_announcements')):
            raise PermissionDenied('Editor permission is required.')

    def get(self, request):
        return Response(dict(editions=list(CampEdition.objects.order_by('-year', '-pk').values('id', 'name')),
            supports=dict(capacity=False, teachers=False, assignment_ending=False,
                audience_selection=False, approval_submission=False, content_versions=False),
            academic_eligibility='Registered non-tutor camper in this edition, as defined by the existing academic assignment validator.'))


class OperationsClassesView(LaunchOperationsBase):
    def get(self, request):
        edition = edition_for(request)
        rows = AcademicClass.objects.filter(edition=edition).annotate(assigned_count=Count('academicassignment')).order_by('name', 'pk')
        if request.query_params.get('q'):
            rows = rows.filter(name__icontains=request.query_params['q'].strip()[:120])
        active = request.query_params.get('active', '')
        if active not in ('', 'true', 'false'):
            raise ValidationError('Choose all, active or inactive classes.')
        if active:
            rows = rows.filter(active=active == 'true')
        page = page_of(rows, request)
        page['results'] = [class_row(row) for row in page['results']]
        return Response(page)

    def post(self, request):
        data = validated(ClassInput, request.data)
        if data.pop('version', None):
            raise ValidationError('A new class must not specify a version.')
        row = AcademicClass(edition=edition_for(request), **data)
        call_service(save_academic, row, request.user)
        return Response(class_row(row), status=201)


class OperationsClassDetailView(LaunchOperationsBase):
    def post(self, request, class_id):
        data = validated(ClassInput, request.data)
        expected = require_version(data)
        row = AcademicClass.objects.filter(pk=class_id, edition=edition_for(request)).first()
        if not row:
            raise NotFound('Class unavailable in this edition.')
        row.name, row.active = data['name'], data['active']
        call_service(save_academic, row, request.user, expected=expected)
        return Response(class_row(row))


class OperationsAssignmentsView(LaunchOperationsBase):
    def get(self, request):
        edition = edition_for(request)
        registered = RegistrationOrderItem.objects.filter(order__edition=edition).exclude(order__registration_basis='tutor')
        rows = Participant.objects.filter(pk__in=registered.values('participant_id')).order_by('full_name', 'pk')
        assignments = AcademicAssignment.objects.filter(edition=edition).select_related('academic_class')
        if request.query_params.get('q'):
            rows = rows.filter(full_name__icontains=request.query_params['q'].strip()[:200])
        mode = request.query_params.get('assignment_state', '')
        if mode not in ('', 'unassigned', 'assigned', 'inactive_class'):
            raise ValidationError('Choose a valid assignment filter.')
        if mode == 'unassigned':
            rows = rows.exclude(pk__in=assignments.values('participant_id'))
        elif mode:
            rows = rows.filter(pk__in=assignments.filter(academic_class__active=mode == 'assigned').values('participant_id'))
        class_id = request.query_params.get('academic_class')
        if class_id:
            class_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1).run_validation(class_id)
            rows = rows.filter(pk__in=assignments.filter(academic_class_id=class_id).values('participant_id'))
        page = page_of(rows, request)
        assigned = {str(row.participant_id): row for row in assignments.filter(participant_id__in=[p.pk for p in page['results']])}
        result = []
        for camper in page['results']:
            row = assigned.get(str(camper.pk))
            result.append(dict(id=str(camper.pk), name=camper.full_name,
                assignment=dict(id=row.pk, academic_class=row.academic_class_id, class_name=row.academic_class.name,
                    active=row.academic_class.active, version=row.updated_at.isoformat()) if row else None))
        page['results'] = result
        return Response(page)

    @transaction.atomic
    def post(self, request):
        data = validated(AssignmentInput, request.data)
        edition = edition_for(request)
        # Serialize lookup and creation with Admin and service writes for this edition.
        CampEdition.objects.select_for_update().get(pk=edition.pk)
        class_id = data['academic_class']
        target = AcademicClass.objects.filter(pk=class_id, edition=edition, active=True).first()
        if not target:
            raise ValidationError('Choose an active class in this edition.')
        assignment_id = data.get('assignment')
        expected = require_version(data) if assignment_id else None
        if not assignment_id and data.get('version'):
            raise ValidationError('A new assignment cannot specify a version.')
        if assignment_id:
            row = AcademicAssignment.objects.filter(pk=assignment_id, edition=edition, participant_id=data['participant']).first()
            if not row:
                raise NotFound('Assignment unavailable in this edition.')
            if row.academic_class_id == target.pk:
                raise ValidationError('Choose a different class for a transfer.')
            row.academic_class = target
        else:
            row = AcademicAssignment(edition=edition, participant_id=data['participant'], academic_class=target)
        call_service(save_academic, row, request.user, expected=expected, reason=data['reason'])
        return Response(dict(id=row.pk, version=row.updated_at.isoformat()), status=200 if assignment_id else 201)


class OperationsAnnouncementsView(LaunchOperationsBase):
    domain = 'announcements'

    def get(self, request):
        rows = CampAnnouncement.objects.filter(edition=edition_for(request)).order_by('-created_at', '-pk')
        status = request.query_params.get('status', '')
        if status not in ('', 'draft', 'published'):
            raise ValidationError('Choose draft or published status.')
        if request.query_params.get('audience', '') not in ('', 'edition'):
            raise ValidationError('Only the existing edition audience is supported.')
        if status:
            rows = rows.filter(status=status)
        if request.query_params.get('q'):
            query = request.query_params['q'].strip()[:160]
            rows = rows.filter(Q(title__icontains=query) | Q(body__icontains=query))
        page = page_of(rows, request)
        page['results'] = [announcement_row(row) for row in page['results']]
        return Response(page)

    def post(self, request):
        call_service(require_launch_permission, request.user, 'manage_dic_announcements')
        data = validated(DraftInput, request.data)
        if data.pop('version', None):
            raise ValidationError('A new draft must not specify a version.')
        row = CampAnnouncement(edition=edition_for(request), **data)
        call_service(save_announcement_draft, row, request.user)
        return Response(announcement_row(row), status=201)


class OperationsAnnouncementDetailView(LaunchOperationsBase):
    domain = 'announcements'

    def post(self, request, announcement_id):
        call_service(require_launch_permission, request.user, 'manage_dic_announcements')
        data = validated(DraftInput, request.data)
        expected = require_version(data)
        row = CampAnnouncement.objects.filter(pk=announcement_id, edition=edition_for(request)).first()
        if not row:
            raise NotFound('Announcement unavailable in this edition.')
        for key, value in data.items():
            setattr(row, key, value)
        call_service(save_announcement_draft, row, request.user, expected=expected)
        return Response(announcement_row(row))


class OperationsAnnouncementPublicationView(LaunchOperationsBase):
    domain = 'announcements'

    def post(self, request, announcement_id):
        call_service(require_launch_permission, request.user, 'publish_dic_announcements')
        data = validated(PublicationInput, request.data)
        row = call_service(publish_announcement, edition_for(request).pk, announcement_id,
            request.user, data['action'], expected=data['version'], reason=data['reason'])
        return Response(announcement_row(row))


class OperationsLaunchHistoryView(LaunchOperationsBase):
    def get(self, request, domain):
        if domain not in ('classes', 'announcements'):
            raise NotFound()
        # initial() also checks the domain supplied in the URL before reading history.
        edition = edition_for(request)
        kinds = ('AcademicClass', 'AcademicAssignment') if domain == 'classes' else ('CampAnnouncement',)
        rows = DICAdminAuditEvent.objects.filter(target_type__in=kinds, details__edition=edition.pk).select_related('actor').order_by('-created_at', '-pk')
        page = page_of(rows, request)
        audit_allowed = request.user.has_perm('dic.can_view_dic_audit')
        page['results'] = [dict(id=row.pk, action=row.action, target_type=row.target_type,
            target_id=row.target_id, time=row.created_at.isoformat(), before=row.details.get('before'),
            after=row.details.get('after'), reason=row.details.get('reason', ''),
            **({'actor': row.actor.get_username() if row.actor else None} if audit_allowed else {})) for row in page['results']]
        return Response(page)

    def initial(self, request, *args, **kwargs):
        self.domain = kwargs.get('domain', 'classes')
        super().initial(request, *args, **kwargs)
