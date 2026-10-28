"""Feedback and confidential welfare storage; no automatic configuration/seeding."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AnonymousCamperResponse(models.Model):
    questionnaire_version = models.PositiveSmallIntegerField(default=2)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    day = models.DateField()
    channel = models.CharField(max_length=8, choices=[('daily','Daily'),('final','Final')])
    ratings = models.JSONField()
    answers = models.JSONField(default=dict)

    class Meta:
        default_permissions = ()
        permissions = [('can_view_dic_feedback','Can view DIC feedback summaries'),
            ('can_read_dic_feedback_details','Can read feedback comments and identified responses')]
        constraints = [models.CheckConstraint(condition=Q(channel__in=('daily','final')), name='dic_camper_feedback_channel')]


class CamperFeedbackReceipt(models.Model):
    # No identity, edition, time, response ID or request ID is stored here.
    digest = models.CharField(primary_key=True, max_length=64, editable=False)

    class Meta:
        default_permissions = ()


class LecturerFeedbackAccess(models.Model):
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    lecturer = models.ForeignKey('dic.Lecturer', on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()
        permissions = [('can_configure_dic_feedback','Can configure DIC lecturer feedback access')]
        constraints = [models.UniqueConstraint(fields=('edition','user'), name='dic_lecturer_feedback_account'),
            models.UniqueConstraint(fields=('edition','lecturer'), name='dic_lecturer_feedback_identity')]


class IdentifiedFeedback(models.Model):
    questionnaire_version = models.PositiveSmallIntegerField(default=2)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    lecturer = models.ForeignKey('dic.Lecturer', on_delete=models.PROTECT, null=True, blank=True)
    channel = models.CharField(max_length=8, choices=[('staff','Staff'),('lecturer','Lecturer')])
    day = models.DateField()
    ratings = models.JSONField()
    answers = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        default_permissions = ()
        permissions = [('can_submit_dic_staff_feedback','Can submit identified DIC staff feedback'),
            ('can_submit_dic_lecturer_feedback','Can submit identified DIC lecturer feedback')]
        constraints = [models.UniqueConstraint(fields=('edition','author','channel','day'), name='dic_identified_feedback_once'),
            models.CheckConstraint(condition=Q(channel='staff', lecturer__isnull=True) | Q(channel='lecturer', lecturer__isnull=False), name='dic_feedback_identity_kind')]


class WelfareReport(models.Model):
    affected_participant = models.ForeignKey('dic.Participant', on_delete=models.PROTECT, null=True, blank=True)
    urgency = models.CharField(max_length=12, choices=[('normal','Normal'),('urgent','Urgent')], default='normal')
    preferred_contact = models.CharField(max_length=12, choices=[('none','No preference'),('email','Booking email'),('in_person','In person')], default='none')
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey('dic.CampEdition', on_delete=models.PROTECT)
    reporter_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='dic_welfare_reports')
    reporter_registrant = models.ForeignKey('dic.PrimaryRegistrant', on_delete=models.PROTECT, null=True, blank=True)
    assistance_person = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=16)
    description = models.TextField(max_length=5000)
    status = models.CharField(max_length=8, default='new')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='dic_welfare_assignments')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    version = models.PositiveIntegerField(default=1)
    request_id = models.UUIDField(unique=True, editable=False)

    class Meta:
        default_permissions = ()
        permissions = [('can_submit_dic_welfare','Can submit identified DIC welfare reports'),
            ('can_view_dic_welfare','Can access confidential DIC welfare reports'),
            ('can_manage_dic_welfare','Can manage confidential DIC welfare reports')]
        constraints = [models.CheckConstraint(condition=Q(reporter_user__isnull=False,reporter_registrant__isnull=True) | Q(reporter_user__isnull=True,reporter_registrant__isnull=False), name='dic_welfare_one_reporter'),
            models.CheckConstraint(condition=Q(status__in=('new','review','resolved','closed')), name='dic_welfare_valid_status'),
            models.CheckConstraint(condition=Q(category__in=('health','accommodation','safety','bullying','assistance','other')), name='dic_welfare_valid_category'),
            models.CheckConstraint(condition=Q(urgency__in=('normal','urgent')), name='dic_welfare_valid_urgency'),
            models.CheckConstraint(condition=Q(preferred_contact__in=('none','email','in_person')), name='dic_welfare_valid_contact')]


class WelfareEvent(models.Model):
    report = models.ForeignKey(WelfareReport, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=8)
    note = models.TextField(max_length=3000, blank=True)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        default_permissions = ()
