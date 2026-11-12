"""Preview by default; explicit activation is distinct from deploying code."""
import json
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from dic.models import RegistrationOrder
from dic import order_lifecycle as lifecycle


class Command(BaseCommand):
    help = 'Preview overdue unpaid orders; --activate --apply enables the approved historical 24-hour policy.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--activate', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--actor', type=int)
        parser.add_argument('--database-name')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--after-id', type=int, default=0, help='Preview cursor from the previous batch; no personal data.')

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('Choose a limit between 1 and 1000.')
        if options['activate'] and (not options['apply'] or options['dry_run']):
            raise CommandError('Activation requires --apply without --dry-run.')
        actor = None
        if options['apply'] and not options['dry_run']:
            if options['database_name'] != str(settings.DATABASES['default']['NAME']):
                raise CommandError('Explicit database-name confirmation is required.')
            try:
                actor = get_user_model().objects.get(pk=options['actor'])
                lifecycle.require_manager(actor)
            except (get_user_model().DoesNotExist, PermissionDenied, TypeError):
                raise CommandError('An authorized active lifecycle staff actor is required.') from None
            if options['activate']:
                lifecycle.activate(actor)
            if not lifecycle.activation():
                raise CommandError('Policy is inactive. Review preview, then explicitly activate.')
        candidates = RegistrationOrder.objects.filter(pk__gt=options['after_id'], registration_basis='paid',
            payment_status__in=('pending', 'failed'), created_at__lte=timezone.now()-timedelta(hours=24))
        candidates = candidates.exclude(payment_attempts__status='successful').exclude(expiry_record__isnull=False).order_by('pk')
        count = candidates.count()
        rows = list(candidates[:options['limit']])
        for order in rows:
            state = lifecycle.evidence_state(order)
            if actor:
                # Read-only provider verification before marking archival metadata.
                # Verification uses the existing shared settlement/idempotency path.
                from dic.payment_views import _verify_attempt, PaymentProviderUnavailable
                from dic.payments import PaystackClient
                for attempt in order.payment_attempts.exclude(status='successful'):
                    try:
                        _verify_attempt(attempt, PaystackClient())
                    except PaymentProviderUnavailable:
                        pass  # Preserve uncertainty and original references; never infer failure.
                changed = lifecycle.record_expiry(order.pk, actor)
                state = 'recorded' if changed else 'protected_or_already_recorded'
            self.stdout.write(json.dumps(dict(cursor=order.pk, order=str(order.public_id), deadline=lifecycle.deadline(order).isoformat(), state=state)))
        self.stdout.write(json.dumps(dict(mode='apply' if actor else 'preview', candidates=count,
            shown=len(rows), remaining=max(0, count-len(rows)), next_after_id=rows[-1].pk if rows else None)))
