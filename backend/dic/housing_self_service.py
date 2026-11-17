"""Explicit, scoped, best-effort housing processing on the existing Django web service.

Never runs during Paystack verification or the settlement transaction.
A participant POST may attempt at most one job for their authorised paid booking;
all policy holds stay for a supervisor in Operations. No scheduler or daemon.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError

from .allocation import AllocationError, unallocated_paid_participants
from .housing_service import permitted, require_automation
from .housing_queue import claim_for_participants, process_claim
from .models import CampEdition, HousingJob
from .settlement_evidence import order_has_verified_settlement

logger = logging.getLogger(__name__)


def process_authorized_housing(orders):
    """Process at most one booking-scoped pending job; failures never affect payment or portal."""
    if getattr(settings, 'DAWANA_WEBSITE_ONLY', False):
        return 'awaiting'
    actor_id = getattr(settings, 'DIC_AUTOMATION_ACTOR_ID', 0)
    if type(actor_id) is not int or actor_id <= 0:
        return 'awaiting'
    try:
        actor = get_user_model().objects.get(pk=actor_id, is_active=True, is_staff=True)
        permitted(actor, 'can_process_housing_queue')
        permitted(actor, 'can_allocate_participants')
        # Only authorised booking scope, never unsafely claim jobs for another
        # participant or another edition.
        for order in list(orders)[:10]:
            if (order.registration_basis != 'paid' or order.status != 'confirmed'
                    or order.payment_status != 'paid'
                    or not order_has_verified_settlement(order)):
                continue
            edition = CampEdition.objects.get(pk=order.edition_id)
            require_automation(edition)
            ids = list(order.items.values_list('participant_id', flat=True)[:20])
            # Repair missed post-payment handoffs, but never reset a held,
            # failed, released or previously completed allocation.
            eligible_ids = set(unallocated_paid_participants(edition)
                               .filter(pk__in=ids).values_list('pk', flat=True))
            for participant_id in ids:
                if participant_id in eligible_ids:
                    HousingJob.objects.get_or_create(
                        edition_id=edition.pk, participant_id=participant_id)
            claimed = claim_for_participants(edition.pk, ids, actor)
            if claimed:
                process_claim(*claimed, actor)
                return 'processed'
    except (AllocationError, ValidationError, PermissionDenied, DatabaseError,
            get_user_model().DoesNotExist):
        logger.warning('Housing processing unavailable; booking remains accessible and awaiting allocation.')
    except Exception:
        logger.error('Housing processing failed after independent payment settlement; internal details suppressed.')
    return 'awaiting'


def housing_public_state(participant_id, edition, assigned):
    """Only one public-facing label. Staff reasons never reach camper data."""
    if assigned:
        return {'status': 'assigned', 'message': 'House assigned'}
    # No job is not a payment failure. It may be a freshly settled order,
    # disabled automation, an unapproved configuration, or staff supervision.
    return {'status': 'awaiting', 'message': 'Awaiting house allocation'}
