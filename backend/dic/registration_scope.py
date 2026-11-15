"""Read-only active registration scope for Operations lists and statistics.

Trash and manual Archive are audit states, independent of payment status.
"""
from .models import RegistrationOrder
from .registration_cleanup import deleted_orders, archived_test_orders
from .order_lifecycle import archive_query


def active_orders(queryset=None):
    if queryset is None:
        queryset = RegistrationOrder.objects.all()
    return (queryset.exclude(pk__in=deleted_orders().values('pk'))
        .exclude(pk__in=archived_test_orders().values('pk'))
        .exclude(status='cancelled').exclude(archive_query()))
