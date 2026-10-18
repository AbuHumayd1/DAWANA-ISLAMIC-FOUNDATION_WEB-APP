import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class CampEdition(models.Model):
    class RegistrationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PAUSED = "paused", "Paused"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=150)
    year = models.PositiveSmallIntegerField(unique=True)
    camp_start_date = models.DateField()
    camp_end_date = models.DateField()
    registration_open_date = models.DateField()
    registration_close_date = models.DateField()
    registration_status = models.CharField(
        max_length=10,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.DRAFT,
    )
    is_active = models.BooleanField(default=False)
    general_information = models.JSONField(
        default=dict,
        blank=True,
        help_text="Edition-specific public information stored as a JSON object.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-year",)
        verbose_name = "camp edition"
        verbose_name_plural = "camp editions"
        constraints = [
            models.CheckConstraint(
                condition=Q(camp_end_date__gte=models.F("camp_start_date")),
                name="dic_edition_camp_dates_ordered",
            ),
            models.CheckConstraint(
                condition=Q(
                    registration_close_date__gte=models.F("registration_open_date")
                ),
                name="dic_edition_registration_dates_ordered",
            ),
            models.UniqueConstraint(
                fields=("is_active",),
                condition=Q(is_active=True),
                name="dic_only_one_active_edition",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.year})"

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.camp_start_date
            and self.camp_end_date
            and self.camp_end_date < self.camp_start_date
        ):
            errors["camp_end_date"] = "The camp end date must not precede its start date."

        if (
            self.registration_open_date
            and self.registration_close_date
            and self.registration_close_date < self.registration_open_date
        ):
            errors["registration_close_date"] = (
                "The registration close date must not precede its opening date."
            )

        if not isinstance(self.general_information, dict):
            errors["general_information"] = (
                "General information must be a JSON object."
            )

        if errors:
            raise ValidationError(errors)


class RegistrationCategory(models.Model):
    edition = models.ForeignKey(
        CampEdition,
        on_delete=models.PROTECT,
        related_name="registration_categories",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    maximum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    eligibility_notes = models.TextField(blank=True)
    fee_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Current configured fee in NGN. Registration orders must copy this "
            "value into an immutable fee snapshot when the order is created."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("edition__year", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("edition", "name"),
                name="dic_category_name_unique_per_edition",
            ),
            models.CheckConstraint(
                condition=Q(fee_ngn__gte=0),
                name="dic_category_fee_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(minimum_age__isnull=True) | Q(minimum_age__gte=0),
                name="dic_category_min_age_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(maximum_age__isnull=True) | Q(maximum_age__gte=0),
                name="dic_category_max_age_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(minimum_age__isnull=True)
                    | Q(maximum_age__isnull=True)
                    | Q(maximum_age__gte=models.F("minimum_age"))
                ),
                name="dic_category_age_range_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.edition}"

    def clean(self):
        super().clean()
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.maximum_age < self.minimum_age
        ):
            raise ValidationError(
                {"maximum_age": "Maximum age must not be less than minimum age."}
            )


class House(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    class Purpose(models.TextChoices):
        PARTICIPANTS = "participants", "Participants"
        FATHERS_AND_ADMINS = "fathers_admins", "Fathers and authorised male admins"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RESERVE = "reserve", "Reserve"
        INACTIVE = "inactive", "Inactive"

    edition = models.ForeignKey(
        CampEdition,
        on_delete=models.PROTECT,
        related_name="houses",
    )
    name = models.CharField(max_length=120)
    gender = models.CharField(max_length=6, choices=Gender.choices)
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.PARTICIPANTS,
    )
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank when capacity has not yet been confirmed.",
    )
    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    eligibility_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Edition-specific eligibility configuration as a JSON object.",
    )
    eligibility_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("edition__year", "gender", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("edition", "name"),
                name="dic_house_name_unique_per_edition",
            ),
            models.CheckConstraint(
                condition=Q(capacity__isnull=True) | Q(capacity__gte=0),
                name="dic_house_capacity_nonnegative",
            ),
            models.CheckConstraint(
                condition=~Q(purpose="fathers_admins") | Q(gender="male"),
                name="dic_fathers_admin_house_male",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.edition}"

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.purpose == self.Purpose.FATHERS_AND_ADMINS
            and self.gender != self.Gender.MALE
        ):
            errors["gender"] = (
                "The fathers and authorised male administrators arrangement "
                "must be designated male."
            )

        if not isinstance(self.eligibility_rules, dict):
            errors["eligibility_rules"] = "Eligibility rules must be a JSON object."

        if errors:
            raise ValidationError(errors)


class PrimaryRegistrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "primary registrant"
        verbose_name_plural = "primary registrants"

    def __str__(self):
        return self.full_name or f"Registrant {self.pk}"


class Participant(models.Model):
    class Sex(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"

    class AcademicStatus(models.TextChoices):
        PRIMARY = "Primary Student", "Primary Student"
        SECONDARY = "Secondary Student", "Secondary Student"
        TERTIARY = "Tertiary Student", "Tertiary Student"
        GRADUATE = (
            "Graduate / Completed Tertiary Education",
            "Graduate / Completed Tertiary Education",
        )
        NOT_IN_SCHOOL = "Not Currently in School", "Not Currently in School"

    class Occupation(models.TextChoices):
        CIVIL_SERVANT = "Civil Servant", "Civil Servant"
        BUSINESS = "Business", "Business"
        TRADER = "Trader", "Trader"
        ENTREPRENEUR = "Entrepreneur", "Entrepreneur"

    class MaritalStatus(models.TextChoices):
        SINGLE = "Single", "Single"
        MARRIED = "Married", "Married"
        DIVORCEE = "Divorcee", "Divorcee"
        WIDOW_WIDOWER = "Widow / Widower", "Widow / Widower"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200)
    address = models.TextField()
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=6, choices=Sex.choices)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    academic_status = models.CharField(max_length=50, choices=AcademicStatus.choices)
    occupation = models.CharField(max_length=32, choices=Occupation.choices)
    marital_status = models.CharField(max_length=20, choices=MaritalStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [
            models.CheckConstraint(
                condition=Q(height_cm__gt=0),
                name="dic_participant_height_positive",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__gt=0),
                name="dic_participant_weight_positive",
            ),
        ]

    def __str__(self):
        return self.full_name


class RegistrationOrder(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    primary_registrant = models.ForeignKey(
        PrimaryRegistrant,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    edition = models.ForeignKey(
        CampEdition,
        on_delete=models.PROTECT,
        related_name="registration_orders",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    idempotency_key_digest = models.CharField(max_length=64, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    access_token_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("submitted", "confirmed", "cancelled")),
                name="dic_order_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    payment_status__in=("pending", "paid", "failed", "refunded")
                ),
                name="dic_order_payment_status_valid",
            ),
        ]

    def __str__(self):
        return f"Order {self.public_id}"

    @property
    def total_amount_ngn(self):
        total = self.items.aggregate(total=Sum("fee_snapshot_ngn"))["total"]
        return total or 0


class RegistrationOrderItem(models.Model):
    order = models.ForeignKey(
        RegistrationOrder,
        on_delete=models.PROTECT,
        related_name="items",
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.PROTECT,
        related_name="registration_items",
    )
    category = models.ForeignKey(
        RegistrationCategory,
        on_delete=models.PROTECT,
        related_name="registration_items",
    )
    category_name_snapshot = models.CharField(max_length=120)
    fee_snapshot_ngn = models.DecimalField(max_digits=12, decimal_places=2)
    participant_snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "participant"),
                name="dic_order_participant_unique",
            ),
            models.CheckConstraint(
                condition=Q(fee_snapshot_ngn__gte=0),
                name="dic_order_item_fee_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.participant} — {self.category_name_snapshot}"

    def clean(self):
        super().clean()
        if (
            self.order_id
            and self.category_id
            and self.order.edition_id != self.category.edition_id
        ):
            raise ValidationError(
                {"category": "The category must belong to the order edition."}
            )

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "order_id",
                "participant_id",
                "category_id",
                "category_name_snapshot",
                "fee_snapshot_ngn",
                "participant_snapshot",
            ).first()
            if previous and any(
                previous[field] != getattr(self, field)
                for field in (
                    "order_id",
                    "participant_id",
                    "category_id",
                    "category_name_snapshot",
                    "fee_snapshot_ngn",
                    "participant_snapshot",
                )
            ):
                raise ValidationError(
                    "Registration order items and fee snapshots are immutable."
                )
        else:
            if self.category_id:
                self.category_name_snapshot = self.category.name
                self.fee_snapshot_ngn = self.category.fee_ngn
            if self.participant_id:
                participant = self.participant
                self.participant_snapshot = {
                    "full_name": participant.full_name,
                    "address": participant.address,
                    "phone": participant.phone,
                    "email": participant.email,
                    "date_of_birth": participant.date_of_birth.isoformat(),
                    "sex": participant.sex,
                    "height_cm": str(participant.height_cm),
                    "weight_kg": str(participant.weight_kg),
                    "academic_status": participant.academic_status,
                    "occupation": participant.occupation,
                    "marital_status": participant.marital_status,
                }
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registration order items cannot be deleted.")
