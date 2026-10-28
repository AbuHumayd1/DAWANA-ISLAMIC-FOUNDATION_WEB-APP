"""Django credentials with explicit booking bindings; no new camper identity."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class PortalAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    username_key = models.CharField(max_length=40, unique=True)
    login_email = models.EmailField(null=True, blank=True, unique=True)
    contact_channel = models.CharField(max_length=10)
    contact_digest = models.CharField(max_length=64)
    credential_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=('contact_channel', 'contact_digest'), name='dic_portal_account_contact')]


class PortalAccountBooking(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.PROTECT, related_name='bookings')
    order = models.OneToOneField('dic.RegistrationOrder', on_delete=models.PROTECT)
    verified_at = models.DateTimeField(default=timezone.now, editable=False)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()


class PortalAccountSession(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.PROTECT)
    grant = models.OneToOneField('dic.ParticipantPortalGrant', on_delete=models.PROTECT)
    credential_version = models.PositiveIntegerField()
    method = models.CharField(max_length=10, choices=[('password', 'Password'), ('google', 'Google')])

    class Meta:
        default_permissions = ()


class PortalGoogleLink(models.Model):
    account = models.OneToOneField(PortalAccount, on_delete=models.PROTECT)
    subject = models.CharField(max_length=255, unique=True)
    linked_at = models.DateTimeField(default=timezone.now, editable=False)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()


class PortalOAuthAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state_digest = models.CharField(max_length=64, unique=True)
    nonce_digest = models.CharField(max_length=64)
    browser_digest = models.CharField(max_length=64)
    encrypted_verifier = models.TextField()
    intent = models.CharField(max_length=5, choices=[('login', 'Login'), ('link', 'Link')])
    grant = models.ForeignKey('dic.ParticipantPortalGrant', null=True, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    remember_device = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()
