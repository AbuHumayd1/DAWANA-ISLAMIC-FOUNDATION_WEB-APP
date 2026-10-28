"""Tutor entitlement is independent of payment and never grants staff authority."""
import uuid
from django.conf import settings
from django.db import models


class TutorRegistrationAuthorization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    intended_name = models.CharField(max_length=200)
    email = models.EmailField(help_text='Authorized email; ownership must be verified before registration.')
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', editable=False)
    authorized_at = models.DateTimeField(editable=False)
    reason = models.TextField()
    invitation_digest = models.CharField(max_length=64, unique=True, null=True, editable=False)
    issued_at = models.DateTimeField(null=True, editable=False)
    expires_at = models.DateTimeField(null=True, editable=False)
    redeemed_at = models.DateTimeField(null=True, editable=False)
    verified_at = models.DateTimeField(null=True, editable=False)
    enrollment = models.OneToOneField('dic.CampEnrollment', null=True, blank=True, on_delete=models.PROTECT, editable=False)
    revoked_at = models.DateTimeField(null=True, editable=False)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+', editable=False)
    revocation_reason = models.TextField(blank=True, editable=False)

    class Meta:
        default_permissions = ()
        permissions = [('can_authorize_dic_tutors', 'Can authorize, reissue and revoke DIC tutors')]
        constraints = [models.UniqueConstraint(fields=('edition', 'email'), condition=models.Q(revoked_at__isnull=True), name='dic_tutor_active_contact')]


class TutorVerification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authorization = models.ForeignKey(TutorRegistrationAuthorization, on_delete=models.PROTECT)
    invitation_digest = models.CharField(max_length=64)
    browser_digest = models.CharField(max_length=64)
    code_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True)
    capability_digest = models.CharField(max_length=64, blank=True)
    request_fingerprint = models.CharField(max_length=64, blank=True)

    class Meta:
        default_permissions = ()
