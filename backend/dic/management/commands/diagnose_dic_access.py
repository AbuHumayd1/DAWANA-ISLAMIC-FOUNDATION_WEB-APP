"""Read-only, privacy-preserving diagnostics for a specific reviewed account."""
import getpass
import json
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from dic.models import PortalAccount, PortalAccountBooking
from dic.recovery import normalize_email
from dic.recovery_views import _contact_digest


class Command(BaseCommand):
    help = 'Read account-state flags only. Never prints credentials, email, contacts, tokens or participant details.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--check-booking-contact', action='store_true', help='Privately prompt for the booking email; never print it.')

    def handle(self, *args, **options):
        identifier = options['username'].strip().lower()
        account = PortalAccount.objects.select_related('user').filter(
            Q(username_key__iexact=identifier) | Q(user__username__iexact=identifier)).first()
        result = {'account_found': bool(account)}
        if account:
            from dic.registration_accounts import pending_registration
            result.update(active=account.user.is_active, privileged=account.user.is_staff or account.user.is_superuser,
                has_password=account.user.has_usable_password(), username_mapping_matches=account.username_key.lower() == identifier,
                verification_pending=pending_registration(account), contact_channel=account.contact_channel,
                linked_bookings=PortalAccountBooking.objects.filter(account=account, revoked_at__isnull=True).count(),
                unpaid_bookings=PortalAccountBooking.objects.filter(account=account, revoked_at__isnull=True,
                    order__status='submitted', order__payment_status__in=['pending', 'failed']).count())
        if options['check_booking_contact']:
            try:
                digest = _contact_digest('email', normalize_email(getpass.getpass('Booking email (hidden): ')))
            except (ValueError, EOFError):
                raise CommandError('A valid reviewed booking contact is required.') from None
            result['booking_contact_matches'] = bool(account and account.contact_channel in ('email', 'username') and account.contact_digest == digest)
            result['contact_already_has_username_account'] = PortalAccount.objects.filter(contact_channel='username', contact_digest=digest).exists()
        self.stdout.write(json.dumps(result, sort_keys=True))
