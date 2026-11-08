"""Small database handoff to existing services; never initializes or verifies payments."""
from .models import HousingJob, HouseAllocation, PortalAccountBooking


def enqueue_housing(order):
    """Called inside settlement's order lock/transaction. Never reset held work."""
    if order.registration_basis != 'paid' or order.payment_status != 'paid' or order.status != 'confirmed':
        return
    for item in order.items.all():
        if not HouseAllocation.objects.filter(edition_id=order.edition_id,
                participant_id=item.participant_id, status='allocated').exists():
            HousingJob.objects.get_or_create(edition_id=order.edition_id, participant_id=item.participant_id)


def status(order):
    """Read-only customer status; payment and identity proof remain independent."""
    if order.payment_status != 'paid' or order.status != 'confirmed':
        return None
    ids = list(order.items.values_list('participant_id', flat=True))
    allocated = HouseAllocation.objects.filter(edition_id=order.edition_id,
        participant_id__in=ids, status='allocated').count()
    jobs = HousingJob.objects.filter(edition_id=order.edition_id, participant_id__in=ids)
    housing = ('ready' if ids and allocated == len(ids) else
               'review' if jobs.filter(state__in=['held', 'failed']).exists() else 'pending')
    binding = PortalAccountBooking.objects.select_related('account__user').filter(order=order,
        revoked_at__isnull=True).first()
    portal = 'pending'
    from .portal_accounts import enabled, booking_eligible
    if binding and not binding.account.user.is_staff and not binding.account.user.is_superuser:
        portal = ('ready' if enabled() and binding.account.user.is_active and booking_eligible(order)
                  else 'verification_required' if not binding.account.user.is_active else 'pending')
        if portal != 'ready' and (binding.account.verification_delivery_at or binding.account.verification_delivery_attempts >= 5):
            portal = 'delivery_pending'
    return {'housing': housing, 'portal': portal}
