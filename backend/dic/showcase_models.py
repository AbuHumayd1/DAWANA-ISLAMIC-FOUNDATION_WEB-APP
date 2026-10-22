"""Editorial content only; never links lecturers or activities to participants."""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from .memory_storage import private_memory_storage, validate_photo


class Lecturer(models.Model):
    name = models.CharField(max_length=200)
    photograph = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200)
    alt_text = models.CharField(max_length=250)
    biography = models.TextField(max_length=2000)
    designation = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            old = Lecturer.objects.select_for_update().get(pk=self.pk)
            fields = ("name", "photograph", "alt_text", "biography", "designation")
            if any(str(getattr(old, key)) != str(getattr(self, key)) for key in fields) or not self.photograph._committed:
                LecturerAppearance.objects.filter(lecturer=self, state="published").update(state="review", published_by=None, published_at=None, updated_at=timezone.now())
                LecturerAppearance.objects.filter(lecturer=self, confirmation_status="confirmed").update(confirmation_status="pending", verified_by=None, verified_at=None)
        super().save(*args, **kwargs)


class ModeratedShowcase(models.Model):
    state = models.CharField(max_length=12, choices=[("draft", "Draft"), ("review", "Ready for review"), ("published", "Published")], default="draft")
    featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-featured", "display_order", "pk")

    def save(self, *args, actor=None, **kwargs):
        if self.state == "published":
            if actor is None or not actor.is_active or not actor.has_perm(f"dic.publish_{self._meta.model_name}"):
                raise PermissionDenied("Separate showcase publication permission is required.")
            self.published_by, self.published_at = actor, timezone.now()
        else:
            self.published_by = self.published_at = None
        super().save(*args, **kwargs)


class LecturerAppearance(ModeratedShowcase):
    lecturer = models.ForeignKey(Lecturer, on_delete=models.PROTECT, related_name="appearances")
    edition = models.ForeignKey("dic.CampEdition", on_delete=models.PROTECT)
    participation_type = models.CharField(max_length=12, choices=[("previous", "Previous edition"), ("upcoming", "Upcoming edition")])
    topic = models.CharField(max_length=300, blank=True)
    confirmation_status = models.CharField(max_length=12, choices=[("pending", "Pending"), ("invited", "Invited"), ("confirmed", "Verified participation"), ("declined", "Declined")], default="pending")
    verification_note = models.TextField(blank=True, help_text="Private evidence/reason for verifying participation and the lecture topic. Never public.")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta(ModeratedShowcase.Meta):
        abstract = False
        permissions = [("publish_lecturerappearance", "Can publish lecturer appearances"), ("verify_lecturerappearance", "Can verify lecturer participation and topics")]
        constraints = [models.UniqueConstraint(fields=("lecturer", "edition"), name="dic_one_lecturer_appearance_per_edition")]

    def __str__(self):
        return f"{self.lecturer} — {self.edition}"

    def clean(self):
        super().clean()
        if self.state == "published" and self.confirmation_status == "declined":
            raise ValidationError("Declined invitations must not be published.")

    @property
    def verified(self):
        return bool(self.confirmation_status == "confirmed" and self.verified_by_id and self.verified_at and self.verification_note.strip())

    @transaction.atomic
    def save(self, *args, actor=None, **kwargs):
        # Same lock order as identity editing and publication.
        Lecturer.objects.select_for_update().get(pk=self.lecturer_id)
        old = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
        changed = old and any(getattr(old, field) != getattr(self, field) for field in ("lecturer_id", "edition_id", "topic", "participation_type", "verification_note"))
        verifying = self.confirmation_status == "confirmed" and (not old or old.confirmation_status != "confirmed" or changed)
        if verifying:
            if actor is None or not actor.is_active or not actor.has_perm("dic.verify_lecturerappearance"):
                raise PermissionDenied("Explicit lecturer verification permission is required.")
            if not self.verification_note.strip():
                raise ValidationError("Record verification evidence before confirming participation.")
            self.verified_by, self.verified_at = actor, timezone.now()
        elif self.confirmation_status != "confirmed":
            self.verified_by = self.verified_at = None
        self.clean()
        super().save(*args, actor=actor, **kwargs)


class CampActivity(ModeratedShowcase):
    edition = models.ForeignKey("dic.CampEdition", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=2000)
    category = models.CharField(max_length=100, help_text="Committee-approved category; no programme categories are seeded.")
    photograph = models.FileField(storage=private_memory_storage, validators=[validate_photo], max_length=200, blank=True)
    alt_text = models.CharField(max_length=250, blank=True)

    class Meta(ModeratedShowcase.Meta):
        abstract = False
        permissions = [("publish_campactivity", "Can approve and publish camp activities")]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.photograph and not self.alt_text.strip():
            raise ValidationError({"alt_text": "Describe the approved activity image."})
