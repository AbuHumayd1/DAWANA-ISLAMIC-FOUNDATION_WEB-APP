"""Username credentials and explicit booking ownership; never payment entitlement."""
import secrets
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed
from . import portal_accounts as accounts
from .models import PortalAccount, PortalAccountBooking, DICAdminAuditEvent
from .recovery import normalize_email
from .recovery_views import _contact_digest


def pending_registration(account):
    """Legacy unverified accounts are never silently activated by the cutover."""
    events = DICAdminAuditEvent.objects.filter(target_type='PortalAccount', target_id=str(account.pk))
    return (not account.user.is_active and not account.user.is_staff and not account.user.is_superuser
        and events.filter(action='portal_account_registration_pending').exists()
        and not events.filter(action__in=('portal_account_email_verified', 'portal_account_password_reset',
            'portal_account_credential_transition')).exists())


@transaction.atomic
def process_verification_delivery(account_id):
    # Compatibility for already queued jobs: retire them without sending or
    # claiming delivery, and without activating a legacy identity.
    account = PortalAccount.objects.select_for_update().filter(pk=account_id).first()
    if not account or not account.verification_delivery_at:
        return 'skipped'
    account.verification_delivery_at = None
    account.save(update_fields=['verification_delivery_at'])
    accounts.audit(account, 'verification_delivery_suppressed')
    return 'suppressed'


@transaction.atomic
@sensitive_variables()
def bind_registration(order, credentials):
    accounts.require_accounts()
    username = accounts.normalize_username(credentials['username'])
    email = normalize_email(order.primary_registrant.email)
    digest = _contact_digest('email', email)
    account = PortalAccount.objects.select_for_update().select_related('user').filter(username_key__iexact=username).first()
    mode = credentials.get('mode', 'auto')
    if account:
        # A retried create request may bind only its already-owned order.
        if mode == 'create' and not PortalAccountBooking.objects.filter(account=account, order=order, revoked_at__isnull=True).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'username': 'Choose another username, or use your existing account.'})
        account = accounts.password_account(username, credentials['password'])
        if account.contact_channel not in ('email', 'username') or not secrets.compare_digest(account.contact_digest, digest):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'primary_registrant': {'email': 'Use the original booking email for this participant account. To change it, recover your existing booking or contact DIC support.'}})
    else:
        if mode == 'existing':
            # Equalize hash work and never turn a failed sign-in into signup.
            accounts.password_account(username, credentials['password'])
        # Contact details are not a verified identity or an account lookup key.
        # A distinct channel prevents username activation from implying email proof.
        user = get_user_model()(username=username, email=email, is_active=True, is_staff=False, is_superuser=False)
        accounts.password_policy(credentials['password'], user)
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise AuthenticationFailed(accounts.INVALID)
        user.set_password(credentials['password'])
        try:
            with transaction.atomic():
                user.save()
                account = PortalAccount.objects.create(user=user, username_key=username, login_email=None,
                    contact_channel='username', contact_digest=digest)
                accounts.audit(account, 'registered')
        except IntegrityError:
            raise AuthenticationFailed(accounts.INVALID) from None
    binding, created = PortalAccountBooking.objects.get_or_create(order=order, defaults={'account': account})
    if binding.account_id != account.pk or binding.revoked_at:
        raise AuthenticationFailed(accounts.INVALID)
    if created:
        accounts.audit(account, 'registration_linked', order=str(order.public_id))
