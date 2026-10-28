"""Staff-only exports; an export is never evidence of physical printing."""
import uuid
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .operations_api import OperationsBaseView
from .identity_cards import card_context, current_issue, require_staff
from .identity_views import secured
from .models import CampEnrollment, DICAdminAuditEvent, RegistrationOrder, Participant, DigitalIDIssue
from .participant_services import eligibility
from .portrait_pdf import house_details, render_pdf, require_pdf_dependencies


def printable(enrollment, issue):
    return bool(issue and issue.verification_digest and issue.verification_secret
        and issue.expires_at > timezone.now() and eligibility(enrollment)['eligible'])


def history():
    return DICAdminAuditEvent.objects.filter(action__in=['participant_ids_exported', 'participant_ids_printed'])


class PrintingDirectoryView(OperationsBaseView):
    def get(self, request):
        require_staff(request.user, manage=True)
        exported, printed = set(), set()
        prior_exported, prior_printed, unversioned = set(), set(), set()
        events = list(history().select_related('actor'))
        for event in events:
            is_printed = event.action.endswith('_printed')
            (prior_printed if is_printed else prior_exported).update(event.details.get('enrollment_ids', []))
            if 'cards' not in event.details:
                unversioned.update(event.details.get('enrollment_ids', []))
            for card in event.details.get('cards', []):
                (printed if is_printed else exported).add((card['enrollment_id'], card['issue_id']))
        rows = []
        for enrollment in CampEnrollment.objects.select_related('participant', 'edition', 'source_item__category').order_by('participant_number'):
            issue = current_issue(enrollment)
            if not printable(enrollment, issue):
                continue
            house, colour = house_details(enrollment)
            key = (str(enrollment.pk), str(issue.pk))
            rows.append(dict(id=str(enrollment.pk), name=enrollment.participant.full_name,
                participant_number=enrollment.participant_number, house=house, colour=colour,
                category=enrollment.source_item.category.name, edition=enrollment.edition.name,
                version=issue.version, exported=key in exported, printed=key in printed,
                previously_exported=str(enrollment.pk) in prior_exported,
                previously_printed=str(enrollment.pk) in prior_printed,
                legacy_history=str(enrollment.pk) in unversioned))
        return Response({'results': rows, 'history': [dict(id=e.target_id, action=e.action,
            actor=e.actor.get_username() if e.actor else 'Deleted account', timestamp=e.created_at,
            **e.details) for e in events[:100]]})


class PrintingExportView(OperationsBaseView):
    @transaction.atomic
    def post(self, request):
        require_staff(request.user, manage=True)
        require_pdf_dependencies()
        ids = request.data.get('enrollment_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 5000:
            raise ValidationError('Select between 1 and 5,000 eligible participants.')
        try:
            ids = list(dict.fromkeys(uuid.UUID(str(value)) for value in ids))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Invalid participant selection.') from None
        initial = list(CampEnrollment.objects.filter(pk__in=ids))
        if len(initial) != len(ids):
            raise ValidationError('Selection changed. Refresh the participant directory.')
        # Match issuance lock order and freeze eligibility / revocation during generation.
        order_ids = RegistrationOrder.objects.filter(items__participant_id__in=[e.participant_id for e in initial]).values_list('pk', flat=True)
        list(RegistrationOrder.objects.select_for_update().filter(pk__in=order_ids).order_by('pk'))
        list(Participant.objects.select_for_update().filter(pk__in=[e.participant_id for e in initial]).order_by('pk'))
        enrollments = list(CampEnrollment.objects.select_for_update().filter(pk__in=ids).order_by('participant_number'))
        list(DigitalIDIssue.objects.select_for_update().filter(enrollment__in=enrollments))
        cards = [card_context(request, e) for e in enrollments]
        payload = render_pdf(cards)
        batch = str(uuid.uuid4())
        DICAdminAuditEvent.objects.create(actor=request.user, action='participant_ids_exported',
            target_type='IDPrintBatch', target_id=batch, details=dict(card_count=len(cards),
                enrollment_ids=[str(e.pk) for e in enrollments],
                participant_numbers=[e.participant_number for e in enrollments], batch_id=batch,
                cards=[dict(enrollment_id=str(card['enrollment'].pk), issue_id=str(card['issue'].pk),
                    version=card['issue'].version, participant_number=card['enrollment'].participant_number)
                    for card in cards]))
        response = HttpResponse(payload, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="dic-id-batch-{batch}.pdf"'
        response['X-ID-Batch'] = batch
        return secured(response)


class PrintingConfirmView(OperationsBaseView):
    @transaction.atomic
    def post(self, request, batch_id):
        require_staff(request.user, manage=True)
        event = DICAdminAuditEvent.objects.select_for_update().filter(
            action='participant_ids_exported', target_id=str(batch_id)).first()
        if not event:
            raise ValidationError('Unknown exported batch.')
        if not history().filter(action='participant_ids_printed', target_id=str(batch_id)).exists():
            DICAdminAuditEvent.objects.create(actor=request.user, action='participant_ids_printed',
                target_type='IDPrintBatch', target_id=str(batch_id), details=event.details)
        return Response({'status': 'printed', 'batch_id': str(batch_id)})
