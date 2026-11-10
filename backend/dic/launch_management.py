"""Shared academic/draft/publication writes for Operations and exceptional Admin use.

No payment, housing, identity or publication side effects outside these records.
Assignment ending/capacity/teachers/audiences require business rules and schema;
they are deliberately not simulated here.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import AcademicClass, AcademicAssignment, CampAnnouncement, CampEdition, DICAdminAuditEvent


class StaleLaunchRecord(ValidationError):
    pass


def require_launch_permission(actor, permission):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_staff
            and actor.has_perm('dic.' + permission)):
        raise PermissionDenied('Explicit active staff permission is required for this action.')


def check_version(row, expected):
    # Operations requires a token. None retains exceptional Admin form behavior;
    # both interfaces serialize writes through the same edition/record locks.
    if expected is not None and row.updated_at.isoformat() != expected:
        raise StaleLaunchRecord('This record changed. Reload before saving; your change was not applied.')


def snapshot(row):
    if isinstance(row, AcademicAssignment):
        return dict(participant=str(row.participant_id), academic_class=row.academic_class_id,
                    class_name=row.academic_class.name)
    if isinstance(row, AcademicClass):
        return dict(name=row.name, active=row.active)
    return dict(title=row.title, body=row.body, status=row.status,
                starts_at=row.starts_at.isoformat() if row.starts_at else None,
                ends_at=row.ends_at.isoformat() if row.ends_at else None)


def audit_launch(row, actor, action, before, reason=''):
    DICAdminAuditEvent.objects.create(actor=actor, action=action,
        target_type=type(row).__name__, target_id=str(row.pk),
        details=dict(edition=row.edition_id, before=before, after=snapshot(row), reason=reason))


@transaction.atomic
def save_academic(row, actor, *, expected=None, reason=''):
    require_launch_permission(actor, 'manage_dic_classes')
    if not isinstance(row, (AcademicClass, AcademicAssignment)):
        raise ValidationError('Only academic class or assignment records are supported.')
    CampEdition.objects.select_for_update().get(pk=row.edition_id)
    before = None
    if row.pk:
        previous = type(row).objects.select_for_update().get(pk=row.pk)
        if previous.edition_id != row.edition_id:
            raise ValidationError('Academic records cannot move to another edition.')
        if isinstance(row, AcademicAssignment) and previous.participant_id != row.participant_id:
            raise ValidationError('An existing assignment cannot be moved to another participant.')
        check_version(previous, expected)
        before = snapshot(previous)
    elif isinstance(row, AcademicAssignment):
        if AcademicAssignment.objects.filter(edition_id=row.edition_id, participant_id=row.participant_id).exists():
            raise StaleLaunchRecord('This camper already has an assignment. Reload and use a reviewed transfer.')
    # Existing model clean/save enforce active, same-edition class and registered
    # non-tutor eligibility. Do not substitute housing/payment/teacher policies.
    row.modified_by = actor
    row.full_clean()
    row.save()
    action = 'academic_class_saved' if isinstance(row, AcademicClass) else 'academic_assignment_saved'
    audit_launch(row, actor, action, before, reason)
    return row


@transaction.atomic
def save_announcement_draft(row, actor, *, expected=None):
    require_launch_permission(actor, 'manage_dic_announcements')
    if not isinstance(row, CampAnnouncement):
        raise ValidationError('Only announcement drafts are supported.')
    CampEdition.objects.select_for_update().get(pk=row.edition_id)
    before = None
    if row.pk:
        previous = CampAnnouncement.objects.select_for_update().get(pk=row.pk)
        if previous.edition_id != row.edition_id:
            raise ValidationError('Announcement edition cannot be changed.')
        check_version(previous, expected)
        if previous.status != 'draft':
            raise ValidationError('Withdraw this announcement before editing its draft.')
        before = snapshot(previous)
    if row.status != 'draft':
        raise ValidationError('Saving content can only save a draft.')
    row.modified_by = actor
    row.full_clean()
    row.save()
    audit_launch(row, actor, 'announcement_draft_saved', before)
    return row


@transaction.atomic
def publish_announcement(edition_id, announcement_id, actor, action, *, expected=None, reason=''):
    require_launch_permission(actor, 'publish_dic_announcements')
    if action not in ('publish', 'withdraw'):
        raise ValidationError('Choose publish or withdraw.')
    CampEdition.objects.select_for_update().get(pk=edition_id)
    row = CampAnnouncement.objects.select_for_update().get(pk=announcement_id, edition_id=edition_id)
    check_version(row, expected)
    target = 'published' if action == 'publish' else 'draft'
    if row.status == target:
        raise ValidationError('This announcement is already in the requested state. Reload it.')
    before = snapshot(row)
    row.status = target
    row.published_by = actor if action == 'publish' else None
    row.modified_by = actor
    row._publication_action = True
    row.save()  # Model remains the authority for time-window and edition validation.
    audit_launch(row, actor, 'announcement_published' if action == 'publish' else 'announcement_unpublished', before, reason)
    return row
