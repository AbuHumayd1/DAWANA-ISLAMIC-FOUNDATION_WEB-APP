"""Credentials authenticate Django users; explicit bindings authorize bookings."""
import re
import secrets
from datetime import timedelta
from types import SimpleNamespace
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError, connection
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied, ValidationError
from .models import (PortalAccount, PortalAccountBooking, PortalAccountSession, PortalGoogleLink, PortalOAuthAttempt,
    ParticipantPortalGrant, ParticipantPortalScope, CampEnrollment, DICAdminAuditEvent, PortalCredentialTransition)
from .security import digest_value
from .portal_phase3 import session_seconds

INVALID = 'Use your existing account username and password. If you cannot sign in, recover your booking or contact DIC support to verify account access.'
RESERVED_USERNAMES = {'admin', 'administrator', 'staff', 'supervisor', 'superuser', 'root',
    'support', 'system', 'dic', 'dif', 'dawana', 'api', 'tutor', 'operations'}


def normalize_username(value):
    if not isinstance(value, str):
        raise ValidationError('Choose a valid username.')
    value = value.strip().lower()
    if (not re.fullmatch(r'[a-z0-9][a-z0-9_. -]{0,39}', value)
            or '  ' in value
            or value in RESERVED_USERNAMES or value.startswith(('dic_', 'admin.', 'staff.'))
            or re.match(r'^(admin(?:istrator)?|staff|dawana|operations)[ ._-]', value)):
        raise ValidationError('Use up to 40 letters, numbers, spaces, dots, hyphens or underscores. Start with a letter or number; official names are reserved.')
    return value


ACCOUNT_TOKEN_PREFIX = 'pa1.'  # Dot cannot occur in existing token_urlsafe OTP credentials.


def enabled():
    return bool(getattr(settings, 'DIC_PORTAL_ACCOUNTS_ENABLED', False))


def require_accounts():
    if not enabled() or not {PortalAccount._meta.db_table, PortalAccountBooking._meta.db_table,
            PortalAccountSession._meta.db_table, PortalGoogleLink._meta.db_table, PortalOAuthAttempt._meta.db_table,
            PortalCredentialTransition._meta.db_table}.issubset(connection.introspection.table_names()):
        error = APIException('Account sign-in awaits approved setup. Contact authorized DIC staff.')
        error.status_code = 503
        raise error


def usable(account):
    return bool(account and account.user.is_active and not account.user.is_staff and not account.user.is_superuser)


def audit(account, action, **details):
    DICAdminAuditEvent.objects.create(actor=account.user, action='portal_account_' + action,
        target_type='PortalAccount', target_id=str(account.pk), details=details)


def rate_limit(request, identifier, operation):
    from .recovery_views import _consume_rate_limit, _rate_key
    # Durable limits commit before authentication errors; never store raw identifiers.
    now = timezone.now()
    with transaction.atomic():
        _consume_rate_limit(_rate_key('portal-'+operation, str(identifier).strip().casefold()), 10, now)
        _consume_rate_limit(_rate_key('portal-'+operation+'-ip', request.META.get('REMOTE_ADDR', 'unknown')), 50, now)


def booking_eligible(order):
    from .participant_services import eligibility
    if order.status != 'confirmed':
        return False
    items = list(order.items.all())
    if not items:
        return False
    for item in items:
        enrollment = CampEnrollment.objects.filter(participant_id=item.participant_id,
            edition_id=order.edition_id, source_item_id=item.pk).first()
        candidate = enrollment or SimpleNamespace(source_item_id=item.pk, participant_id=item.participant_id,
            edition_id=order.edition_id, restriction_reason='', source_review_fingerprint='')
        if not eligibility(candidate)['eligible']:
            return False
    return True


def fresh_otp(request):
    from .participant_api import authorized_grant, scoped_orders
    # Proof is reusable briefly, not consumed. Avoid grant/account lock inversion.
    grant = authorized_grant(request)
    if (grant.created_at < timezone.now()-timedelta(minutes=10)
            or PortalAccountSession.objects.filter(grant=grant).exists()):
        raise PermissionDenied('Verify your booking contact again before changing sign-in methods.')
    orders = scoped_orders(grant)
    if not orders or not all(booking_eligible(order) for order in orders):
        raise PermissionDenied('Verified paid or authorized tutor registration is required.')
    return grant, orders


def proof_channels(channel):
    # A fresh email OTP may recover a username account bound to that same
    # contact snapshot. The account's channel remains unverified username.
    return ('email', 'username') if channel == 'email' else (channel,)


def owned_account(grant, orders, allow_pending=False):
    ids = PortalAccountBooking.objects.filter(order__in=orders, revoked_at__isnull=True).values('account_id')
    account = PortalAccount.objects.select_for_update().select_related('user').filter(pk__in=ids,
        contact_channel__in=proof_channels(grant.channel), contact_digest=grant.contact_digest,
        ).first()
    pending = False
    if allow_pending and account and grant.channel == 'email' and not account.user.is_active:
        from .registration_accounts import pending_registration
        pending = pending_registration(account)
    if not usable(account) and not pending:
        raise PermissionDenied(INVALID)
    return account


def password_policy(password, user):
    # Owner-approved participant policy. Staff validators remain unchanged.
    if not isinstance(password, str) or not password or len(password) > 128:
        raise ValidationError('Enter a nonempty password of at most 128 characters.')


@sensitive_variables()
@transaction.atomic
def activate(request, username, password, email=''):
    require_accounts()
    grant, orders = fresh_otp(request)
    username = normalize_username(username)
    from .recovery import normalize_email
    from .recovery_views import _contact_digest
    email = normalize_email(email)
    if not email or grant.channel != 'email':
        raise PermissionDenied('Verify your booking email before creating an account.')
    if email and (grant.channel != 'email' or not secrets.compare_digest(grant.contact_digest, _contact_digest('email', email))):
        raise PermissionDenied('Verify this email through your booking before using it for sign-in.')
    user = get_user_model()(username=username, email=email, is_staff=False, is_superuser=False, is_active=True)
    if password:
        password_policy(password, user)
        user.set_password(password)
    else:
        raise ValidationError('Set a password to create your portal account.')
    try:
        with transaction.atomic():
            user.save()
            account = PortalAccount.objects.create(user=user, username_key=username.casefold(), login_email=email or None,
                contact_channel=grant.channel, contact_digest=grant.contact_digest)
            for order in orders:
                PortalAccountBooking.objects.create(account=account, order=order)
    except IntegrityError:
        raise ValidationError('Account setup could not be completed. Use verified recovery or a different username.')
    audit(account, 'activated', orders=[str(order.public_id) for order in orders])
    return account


@sensitive_variables()
def password_account(identifier, password):
    query = {'login_email': identifier.strip().lower()} if '@' in identifier else {'username_key__iexact': identifier.strip().lower()}
    account = PortalAccount.objects.select_related('user').filter(**query).first()
    if not account:
        get_user_model()().set_password(password)  # Same password-hash cost; no account enumeration shortcut.
        raise AuthenticationFailed(INVALID)
    checked = account.user.check_password(password)
    if checked and not account.user.is_active:
        from .registration_accounts import pending_registration
        if pending_registration(account):
            raise AuthenticationFailed('This account still needs verification. Recover your existing booking or contact DIC support to complete verification; do not create another booking or pay again.')
    if not checked or not usable(account): raise AuthenticationFailed(INVALID)
    return account


def linked_orders(account):
    from .participant_api import primary_contact_matches
    bindings = PortalAccountBooking.objects.filter(account=account, revoked_at__isnull=True,
        order__access_token_revoked_at__isnull=True).select_related('order__primary_registrant')
    return [binding.order for binding in bindings if primary_contact_matches(binding.order,
        account.contact_channel, account.contact_digest) and booking_eligible(binding.order)]


@transaction.atomic
def issue_session(account, request, method, remember=False):
    from .participant_api import COOKIE
    authenticated_version = account.credential_version
    account = PortalAccount.objects.select_for_update().select_related('user').get(pk=account.pk)
    if not usable(account) or account.credential_version != authenticated_version:
        raise AuthenticationFailed(INVALID)
    orders = linked_orders(account)
    if not orders: raise AuthenticationFailed(INVALID)
    if method == 'google' and not PortalGoogleLink.objects.filter(account=account, revoked_at__isnull=True).exists():
        raise AuthenticationFailed(INVALID)
    token, now = ACCOUNT_TOKEN_PREFIX + secrets.token_urlsafe(32), timezone.now()
    duration = session_seconds(remember)
    ParticipantPortalGrant.objects.filter(credential_digest=digest_value(request.COOKIES.get(COOKIE, '')),
        revoked_at__isnull=True).update(revoked_at=now)
    grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value(token), channel=account.contact_channel,
        contact_digest=account.contact_digest, expires_at=now+timedelta(seconds=duration))
    ParticipantPortalScope.objects.bulk_create([ParticipantPortalScope(grant=grant, order=order) for order in orders])
    PortalAccountSession.objects.create(account=account, grant=grant, credential_version=account.credential_version, method=method)
    audit(account, 'signed_in', method=method, grant=str(grant.pk))
    return grant, token, duration


def account_session(grant):
    if not enabled(): return None
    mapping = PortalAccountSession.objects.select_related('account__user').filter(grant=grant).first()
    if mapping and (not usable(mapping.account) or mapping.credential_version != mapping.account.credential_version
            or (mapping.method == 'google' and not PortalGoogleLink.objects.filter(account=mapping.account, revoked_at__isnull=True).exists())):
        raise AuthenticationFailed('Your participant session has expired. Please verify again.')
    return mapping


@sensitive_variables()
@transaction.atomic
def reset_password(request, password):
    require_accounts()
    grant, orders = fresh_otp(request)
    account = owned_account(grant, orders, allow_pending=True)
    password_policy(password, account.user)
    account.user.set_password(password)
    # Fresh booking email OTP is sufficient one-time email proof for recovery.
    if grant.channel == 'email': account.user.is_active = True
    account.user.save(update_fields=['password', 'is_active'])
    account.credential_version += 1
    account.save(update_fields=['credential_version'])
    ParticipantPortalGrant.objects.filter(portalaccountsession__account=account).update(revoked_at=timezone.now())
    audit(account, 'password_reset')
    return account


@sensitive_variables()
@transaction.atomic
def link_booking(request, identifier, password):
    require_accounts()
    grant, orders = fresh_otp(request)
    account = password_account(identifier, password)
    authenticated_version = account.credential_version
    account = PortalAccount.objects.select_for_update().select_related('user').get(pk=account.pk)
    if not usable(account) or account.credential_version != authenticated_version:
        raise AuthenticationFailed(INVALID)
    if account.contact_channel not in proof_channels(grant.channel) or not secrets.compare_digest(account.contact_digest, grant.contact_digest):
        raise PermissionDenied(INVALID)
    try:
        with transaction.atomic():
            for order in orders:
                binding, _ = PortalAccountBooking.objects.get_or_create(order=order, defaults={'account': account})
                if binding.account_id != account.pk or binding.revoked_at:
                    raise PermissionDenied(INVALID)
    except IntegrityError:
        raise PermissionDenied(INVALID)
    audit(account, 'booking_linked', orders=[str(order.public_id) for order in orders])
    return account
