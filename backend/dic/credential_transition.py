"""Administrator-reviewed recovery in the existing participant account system.

No public identity lookup, email delivery, role changes or payment mutations.
"""
import secrets
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import PermissionDenied, ValidationError
from . import portal_accounts as accounts
from .models import (RegistrationOrder, PortalAccount, PortalAccountBooking,
    PortalCredentialTransition, ParticipantPortalGrant, DICAdminAuditEvent)
from .registration_accounts import pending_registration, bind_registration

INVALID = 'Credential recovery is unavailable. Contact the authorizing administrator.'


def require_owner(actor):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_staff and actor.is_superuser):
        raise PermissionDenied('An active system administrator must review account ownership.')


def recoverable(account):
    return bool(account and not account.user.is_staff and not account.user.is_superuser
        and (accounts.usable(account) or pending_registration(account)))


@transaction.atomic
@sensitive_variables()
def issue(actor, order_reference, reason, password):
    accounts.require_accounts()
    require_owner(actor)
    if not actor.check_password(password) or not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 240:
        raise PermissionDenied('Re-enter your password and record the ownership review reference (10–240 characters).')
    order = RegistrationOrder.objects.select_for_update().get(public_id=order_reference)
    if order.status == 'cancelled' or order.access_token_revoked_at:
        raise PermissionDenied(INVALID)
    binding = PortalAccountBooking.objects.select_related('account__user').filter(order=order).first()
    account = binding.account if binding else None
    if binding and (binding.revoked_at or not recoverable(account)):
        raise PermissionDenied(INVALID)
    if account:
        account = PortalAccount.objects.select_for_update().select_related('user').get(pk=account.pk)
        if not recoverable(account):
            raise PermissionDenied(INVALID)
    now, token = timezone.now(), secrets.token_urlsafe(32)
    # Reissuing invalidates every earlier authority for this account or order.
    query = PortalCredentialTransition.objects.filter(account=account) if account else PortalCredentialTransition.objects.filter(order=order)
    query.filter(consumed_at__isnull=True).update(consumed_at=now)
    row = PortalCredentialTransition.objects.create(order=order, account=account,
        credential_version=account.credential_version if account else None,
        password_digest=accounts.digest_value(account.user.password) if account else '',
        issued_by=actor, token_digest=accounts.digest_value(token), expires_at=now+timedelta(minutes=15))
    DICAdminAuditEvent.objects.create(actor=actor, action='portal_credential_transition_issued',
        target_type='RegistrationOrder', target_id=str(order.public_id),
        details={'transition': row.pk, 'review_reference': reason.strip()})
    return token


@transaction.atomic
@sensitive_variables()
def consume(token, username, password):
    accounts.require_accounts()
    if not isinstance(token, str) or len(token) != 43:
        raise ValidationError(INVALID)
    reference = PortalCredentialTransition.objects.filter(token_digest=accounts.digest_value(token)).first()
    if not reference:
        raise ValidationError(INVALID)
    # Same order -> account -> authority lock order as issuance and registration.
    order = RegistrationOrder.objects.select_for_update().get(pk=reference.order_id)
    account = PortalAccount.objects.select_for_update().select_related('user').filter(pk=reference.account_id).first()
    row = PortalCredentialTransition.objects.select_for_update().select_related('issued_by').get(pk=reference.pk)
    require_owner(row.issued_by)
    if row.consumed_at or row.expires_at <= timezone.now() or order.status == 'cancelled' or order.access_token_revoked_at:
        raise ValidationError(INVALID)
    username = accounts.normalize_username(username)
    binding = PortalAccountBooking.objects.filter(order=order).first()
    if account:
        if (not binding or binding.account_id != account.pk or binding.revoked_at
                or not recoverable(account) or account.credential_version != row.credential_version
                or not secrets.compare_digest(accounts.digest_value(account.user.password), row.password_digest)):
            raise ValidationError(INVALID)
        was_pending = pending_registration(account)
        user = account.user
        if get_user_model().objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            raise ValidationError(INVALID)
        user.username = username
        accounts.password_policy(password, user)
        try:
            with transaction.atomic():
                user.set_password(password)
                user.is_active = True  # Only active or explicitly pending legacy accounts qualify.
                user.save(update_fields=['username', 'password', 'is_active'])
                if was_pending:
                    account.contact_channel = 'username'
                account.username_key = username
                account.credential_version += 1
                account.verification_delivery_at = None
                # Preserve historical contact proof status; do not audit email verification.
                account.save(update_fields=['username_key', 'credential_version', 'verification_delivery_at', 'contact_channel'])
        except IntegrityError:
            raise ValidationError(INVALID) from None
        ParticipantPortalGrant.objects.filter(portalaccountsession__account=account).update(revoked_at=timezone.now())
    else:
        if binding:
            raise ValidationError(INVALID)
        bind_registration(order, {'username': username, 'password': password})
        account = PortalAccountBooking.objects.get(order=order).account
    row.consumed_at = timezone.now()
    row.save(update_fields=['consumed_at'])
    accounts.audit(account, 'credential_transition', transition=row.pk, authorized_by=row.issued_by_id)
    # No session or payment access is issued by a reset.
    return account
