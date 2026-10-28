"""Read-only campsite foundation. No attendance, ledger, scoring or feedback writes."""
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .operations_api import OperationsBaseView, _edition_from_request
from .models import CampEdition, CampEnrollment, RegistrationOrderItem, HouseAllocation, DigitalIDIssue
from .participant_services import eligibility


def require_campsite_staff(user):
    if not (user.is_authenticated and user.is_active and user.is_staff
            and user.has_perm('dic.can_view_dic_operations')):
        raise PermissionDenied('Active authorized campsite staff access is required.')


def campsite_metrics(edition):
    """Use the existing ID eligibility definition without preparing or issuing IDs."""
    items = RegistrationOrderItem.objects.filter(order__edition=edition).select_related(
        'participant', 'order', 'category').order_by('participant_id', 'pk')
    enrollments = {row.participant_id: row for row in CampEnrollment.objects.filter(
        edition=edition).select_related('participant', 'edition', 'source_item')}
    allocated = set(HouseAllocation.objects.filter(edition=edition, status='allocated')
        .values_list('participant_id', flat=True))
    seen, eligible, awaiting_payment, attention, tutors = set(), set(), set(), set(), set()
    for item in items:
        if item.participant_id in seen:
            continue
        seen.add(item.participant_id)
        enrollment = enrollments.get(item.participant_id)
        candidate = enrollment or CampEnrollment(participant=item.participant,
            edition=edition, source_item=item)
        result = eligibility(candidate)
        if item.order.registration_basis == 'tutor':
            tutors.add(item.participant_id)
        if result['eligible']:
            eligible.add(item.participant_id)
        elif result['code'] == 'registration_not_verified_paid' and item.order.status != 'cancelled':
            awaiting_payment.add(item.participant_id)
        else:
            attention.add(item.participant_id)
    active_ids = DigitalIDIssue.objects.filter(enrollment__edition=edition,
        enrollment__participant_id__in=eligible, revoked_at__isnull=True,
        expires_at__gt=timezone.now(), verification_digest__isnull=False).exclude(
            Q(verification_secret='') | Q(verification_digest='')).values('enrollment_id').distinct().count()
    return dict(registered_participants=len(seen), eligible_participants=len(eligible),
        awaiting_payment_verification=len(awaiting_payment),
        complimentary_tutors=len(tutors),
        assigned_participants=len((seen-tutors) & allocated), awaiting_house_assignment=len(eligible-allocated-tutors),
        active_ids=active_ids, requiring_attention=len(attention), attendance=None)


class CampsiteOverviewView(OperationsBaseView):
    def get(self, request):
        require_campsite_staff(request.user)
        edition = _edition_from_request(request)
        editions = list(CampEdition.objects.order_by('-year', '-pk').values('id', 'name', 'year'))
        return Response(dict(
            edition=dict(id=edition.pk, name=edition.name, year=edition.year) if edition else None,
            editions=editions, metrics=campsite_metrics(edition) if edition else None,
            definitions=dict(
                registered_participants='Distinct participants with registration items in this edition, including cancelled registrations.',
                eligible_participants='Existing ID eligibility: confirmed registration, trusted payment evidence and no unresolved source or identity restriction.',
                awaiting_payment_verification='Non-cancelled participants failing the registration/payment state check. Other evidence problems appear under attention.',
                assigned_participants='Registered participants with an active allocation record in this edition; this is not a housing-policy certification.',
                awaiting_house_assignment='Eligible participants without an active allocation record in this edition.',
                active_ids='Eligible participants with an unrevoked, unexpired QR credential. Does not establish attendance.',
                requiring_attention='Ineligible participants requiring review beyond pending registration/payment state, including cancelled registrations.',
                attendance='Unavailable: campsite check-in and attendance are not implemented in Phase 2.1.')))
