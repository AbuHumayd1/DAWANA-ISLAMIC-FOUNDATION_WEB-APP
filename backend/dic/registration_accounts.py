"""Pre-payment credentials; email proof and payment entitlement are independent."""
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import APIException, AuthenticationFailed, ValidationError
from . import portal_accounts as accounts
from .models import PortalAccount, PortalAccountBooking, DICAdminAuditEvent
from .recovery import normalize_email, email_delivery_configured
from .recovery_views import _contact_digest

SALT = 'dic.registration.email.verify.v1'


def require_verification_delivery():
    if not settings.DEBUG and not email_delivery_configured():
        error = APIException('Email verification delivery is temporarily unavailable. Please retry later or contact DIC staff.')
        error.status_code = 503
        raise error


def pending_registration(account):
    events = DICAdminAuditEvent.objects.filter(target_type='PortalAccount', target_id=str(account.pk))
    return (not account.user.is_active and not account.user.is_staff and not account.user.is_superuser
        and events.filter(action='portal_account_registration_pending').exists()
        and not events.filter(action__in=('portal_account_email_verified', 'portal_account_password_reset')).exists())


def verification_url():
    value = getattr(settings, 'DIC_PORTAL_EMAIL_VERIFY_URL', '')
    parsed = urlsplit(value)
    valid = parsed.scheme == 'https' or (settings.DEBUG and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost'))
    if not (valid and parsed.hostname and parsed.path == '/dic/participant' and not parsed.query
            and not parsed.fragment and not parsed.username and not parsed.password):
        raise ValidationError('Email verification awaits configured portal delivery. Contact DIC staff.')
    return value


def email_token(account):
    return signing.dumps({'account': account.pk, 'version': account.credential_version,
        'email': account.contact_digest, 'password': accounts.digest_value(account.user.password)}, salt=SALT, compress=True)


@sensitive_variables()
def deliver_verification(account):
    require_verification_delivery()
    # Never log exceptions or include link tokens in an API response.
    url = verification_url()+'#verify-email='+email_token(account)
    if send_mail('Verify your DIC Camper Portal email',
            'Verify your email using this one-time link (valid for one hour): '+url+
            '\nYour booking must also be eligible: ordinary registrations require independently verified payment; authorized complimentary tutors do not. If you did not register, ignore this message.',
            settings.DEFAULT_FROM_EMAIL, [account.login_email], fail_silently=False) != 1:
        raise ValidationError('Verification email could not be delivered. Retry from portal sign-in.')


@sensitive_variables()
def schedule_verification(account):
    require_verification_delivery()
    # This row survives process termination after commit and a mail outage.
    PortalAccount.objects.filter(pk=account.pk).update(verification_delivery_at=timezone.now(),
        verification_delivery_attempts=0)
    def deliver():
        try:
            process_verification_delivery(account.pk)
        except Exception:
            # Registration/payment capability survives a mail outage. Resending
            # requires the chosen password; no identity or mail details escape.
            return
    transaction.on_commit(deliver)


@transaction.atomic
@sensitive_variables()
def process_verification_delivery(account_id):
    account = PortalAccount.objects.select_for_update(of=('self',), skip_locked=True).select_related('user').filter(pk=account_id).first()
    if not account or not account.verification_delivery_at or account.verification_delivery_at > timezone.now():
        return 'skipped'
    if not pending_registration(account):
        account.verification_delivery_at = None
        account.save(update_fields=['verification_delivery_at'])
        return 'suppressed'
    account.verification_delivery_attempts += 1
    try:
        deliver_verification(account)
    except Exception:
        # A repeated verification link cannot grant entitlement or change payment.
        # Never persist provider exceptions, destinations or signed link tokens.
        account.verification_delivery_at = (timezone.now() + timedelta(
            seconds=min(60 * 2 ** min(account.verification_delivery_attempts, 6), 3600))
            if account.verification_delivery_attempts < 5 else None)
        result = 'pending' if account.verification_delivery_at else 'failed'
    else:
        account.verification_delivery_at = None
        account.verification_delivery_attempts = 0
        result = 'sent'
    account.save(update_fields=['verification_delivery_at', 'verification_delivery_attempts'])
    accounts.audit(account, 'verification_delivery_' + result)
    return result


@sensitive_variables()
def credential_account(email, password):
    email = normalize_email(email)
    account = PortalAccount.objects.select_related('user').filter(login_email=email).first()
    if not account:
        get_user_model()().set_password(password)
        raise AuthenticationFailed(accounts.INVALID)
    if not account.user.check_password(password) or account.user.is_staff or account.user.is_superuser:
        raise AuthenticationFailed(accounts.INVALID)
    if not account.user.is_active and not pending_registration(account):
        raise AuthenticationFailed(accounts.INVALID)
    return account


@transaction.atomic
@sensitive_variables()
def bind_registration(order, credentials):
    accounts.require_accounts()
    email = normalize_email(order.primary_registrant.email)
    digest = _contact_digest('email', email)
    account = PortalAccount.objects.select_for_update().select_related('user').filter(login_email=email).first()
    if account:
        account = credential_account(email, credentials['password'])
        if account.contact_channel != 'email' or not secrets.compare_digest(account.contact_digest, digest):
            raise AuthenticationFailed(accounts.INVALID)
    else:
        username = 'dic_'+secrets.token_hex(16)
        user = get_user_model()(username=username, email=email, is_active=False, is_staff=False, is_superuser=False)
        accounts.password_policy(credentials['password'], user)
        user.set_password(credentials['password'])
        try:
            with transaction.atomic():
                user.save()
                account = PortalAccount.objects.create(user=user, username_key=username, login_email=email,
                    contact_channel='email', contact_digest=digest)
                accounts.audit(account, 'registration_pending')
        except IntegrityError:
            raise ValidationError('Account setup could not be completed. Use existing credentials or verified recovery.')
    binding, created = PortalAccountBooking.objects.get_or_create(order=order, defaults={'account': account})
    if binding.account_id != account.pk or binding.revoked_at:
        raise AuthenticationFailed(accounts.INVALID)
    if created: accounts.audit(account, 'registration_linked', order=str(order.public_id))
    if not account.user.is_active:
        verification_url()  # Fail registration atomically if no safe link destination exists.
        schedule_verification(account)


@transaction.atomic
@sensitive_variables()
def verify_email(token):
    accounts.require_accounts()
    try:
        data = signing.loads(token, salt=SALT, max_age=3600)
        account = PortalAccount.objects.select_for_update().select_related('user').get(pk=data['account'])
        valid = (pending_registration(account)
            and account.credential_version == data['version'] and account.contact_digest == data['email']
            and secrets.compare_digest(accounts.digest_value(account.user.password), data['password']))
    except (signing.BadSignature, KeyError, TypeError, ValueError, PortalAccount.DoesNotExist):
        valid = False
    if not valid: raise ValidationError('Email verification is invalid, expired or already used. Request a new link.')
    account.user.is_active = True
    account.user.save(update_fields=['is_active'])
    accounts.audit(account, 'email_verified')
    # This sets no session/cookie; payment and scope checks still gate login.
