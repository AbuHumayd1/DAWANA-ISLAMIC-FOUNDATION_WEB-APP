"""Central read-only Operations lifecycle; accounting evidence is independent.

Latest successful audit event wins. Trash takes precedence over Archive.
Restoration follows the existing cleanup policy (restoring also clears Archive).
Expired bookings are archived operationally; cancelled status stays separate.
"""
from django.db.models import Case, When, Value, CharField, Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import RegistrationOrder
from .registration_cleanup import deleted_orders, archived_test_orders
from .order_lifecycle import archive_query

LABELS = {'active': 'Active', 'archived': 'Archived', 'deleted': 'Deleted', 'cancelled': 'Cancelled'}


def _lifecycle_conditions():
    # Membership subqueries keep multi-attempt / multi-participant joins distinct.
    return [
        ('deleted', Q(pk__in=deleted_orders().values('pk'))),
        ('archived', Q(pk__in=archived_test_orders().values('pk')) |
            Q(pk__in=RegistrationOrder.objects.filter(archive_query()).values('pk'))),
        ('cancelled', Q(status='cancelled')),
    ]


def lifecycle_orders(queryset=None):
    if queryset is None:
        queryset = RegistrationOrder.objects.all()
    return queryset.annotate(registration_lifecycle=Case(
        *[When(condition, then=Value(state)) for state, condition in _lifecycle_conditions()],
        default=Value('active'), output_field=CharField()))


def active_orders(queryset=None):
    if queryset is None:
        queryset = RegistrationOrder.objects.all()
    # Avoid repeating a CASE expression in deeply nested operational queries.
    for _, condition in _lifecycle_conditions():
        queryset = queryset.exclude(condition)
    return queryset


def lifecycle_state(order):
    state = getattr(order, 'registration_lifecycle', None)
    return state or lifecycle_orders().values_list('registration_lifecycle', flat=True).get(pk=order.pk)


def operations_view(params, user):
    view = params.get('view', 'active')
    if view not in ('active', 'history'):
        raise ValidationError({'view': 'Choose active or history.'})
    if view == 'history' and not user.has_perm('dic.can_view_dic_audit'):
        raise PermissionDenied('Administrative history requires audit permission.')
    return view


def operational_eligibility(candidate):
    from .participant_services import eligibility
    order = lifecycle_orders().filter(items__pk=candidate.source_item_id).first()
    if order is None:
        return {'eligible': False, 'code': 'invalid_source'}
    state = order.registration_lifecycle
    if state != 'active':
        return {'eligible': False, 'code': 'registration_' + state}
    return eligibility(candidate)
