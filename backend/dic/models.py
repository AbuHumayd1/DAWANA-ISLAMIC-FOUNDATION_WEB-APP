import re
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.conf import settings
from django.utils import timezone

from .security import order_access_token_expiry
from .memory_storage import private_memory_storage, private_participant_storage, validate_photo


LAGOS_TIME_ZONE = ZoneInfo("Africa/Lagos")


class CampEdition(models.Model):
    tutor_registration_enabled = models.BooleanField(default=False)
    class RegistrationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PAUSED = "paused", "Paused"
        CLOSED = "closed", "Closed"

    class AllocationStrategy(models.TextChoices):
        DISABLED = "disabled", "Disabled"
        BALANCED = "balanced", "Balanced available capacity"

    name = models.CharField(max_length=150)
    year = models.PositiveSmallIntegerField(unique=True)
    camp_start_date = models.DateField()
    camp_end_date = models.DateField()
    registration_open_date = models.DateField(null=True, blank=True)
    registration_close_date = models.DateField(null=True, blank=True)
    venue_name = models.CharField(max_length=150, blank=True)
    venue_directions_address = models.CharField(max_length=255, blank=True)
    venue_google_place_id = models.CharField(max_length=255, blank=True)
    venue_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    venue_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    venue_directions_verified = models.BooleanField(default=False)
    venue_directions_verified_at = models.DateTimeField(null=True, blank=True)
    venue_directions_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="verified_dic_venues",
        null=True,
        blank=True,
    )
    early_bird_cutoff_at = models.DateTimeField(null=True, blank=True)
    registration_status = models.CharField(
        max_length=10,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.DRAFT,
    )
    is_active = models.BooleanField(default=False)
    allocation_strategy = models.CharField(
        max_length=12,
        choices=AllocationStrategy.choices,
        default=AllocationStrategy.DISABLED,
    )
    allocation_strategy_approved_at = models.DateTimeField(null=True, blank=True)
    allocation_strategy_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_dic_allocation_strategies",
        null=True,
        blank=True,
    )
    allocation_strategy_approval_note = models.TextField(blank=True)
    allocation_approved_configuration = models.CharField(max_length=64, blank=True)
    housing_age_reference_date = models.DateField(null=True, blank=True,
        help_text="Housing age reference date; DIC 2026 uses 23 December 2026.")
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
        permissions = [
            ("can_edit_confirmed_dic_details", "Can edit confirmed DIC edition details"),
            ("can_view_dic_operations", "Can view DIC operations dashboard"),
            ("can_view_dic_finance", "Can view DIC payment operations"),
            ("can_view_dic_contact_information", "Can view DIC participant contact information"),
            ("can_export_dic_reports", "Can export DIC registration reports"),
            ("can_export_dic_contact_information", "Can export DIC contact information"),
            ("can_view_dic_audit", "Can view DIC administrative audit events"),
            ("can_manage_registration_access", "Can revoke DIC registration access"),
        ]
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

        if bool(self.venue_latitude is not None) != bool(self.venue_longitude is not None):
            errors["venue_longitude"] = (
                "Enter both coordinates or leave both coordinates blank."
            )
        if self.venue_latitude is not None and not Decimal("-90") <= self.venue_latitude <= Decimal("90"):
            errors["venue_latitude"] = "Latitude must be between -90 and 90."
        if self.venue_longitude is not None and not Decimal("-180") <= self.venue_longitude <= Decimal("180"):
            errors["venue_longitude"] = "Longitude must be between -180 and 180."
        if self.venue_google_place_id and not re.fullmatch(
            r"[A-Za-z0-9_-]{1,255}",
            self.venue_google_place_id,
        ):
            errors["venue_google_place_id"] = (
                "Enter a valid Google Maps place identifier."
            )
        destinations = sum(
            bool(value)
            for value in (
                self.venue_directions_address.strip(),
                self.venue_google_place_id.strip(),
                self.venue_latitude is not None and self.venue_longitude is not None,
            )
        )
        if destinations > 1:
            errors["venue_directions_address"] = (
                "Configure only one verified directions destination."
            )
        if self.venue_directions_verified and not destinations:
            errors["venue_directions_verified"] = (
                "A directions destination is required before it can be verified."
            )
        if self.early_bird_cutoff_at and timezone.is_naive(self.early_bird_cutoff_at):
            errors["early_bird_cutoff_at"] = (
                "The early-bird cutoff must include a timezone."
            )

        if not isinstance(self.general_information, dict):
            errors["general_information"] = (
                "General information must be a JSON object."
            )

        if errors:
            raise ValidationError(errors)

    def pricing_configuration_errors(self, *, categories=None):
        errors = {}
        if not self.registration_open_date or not self.registration_close_date:
            errors["registration_open_date"] = (
                "Registration dates must be configured before opening registration."
            )
        if self.registration_open_date and self.registration_close_date:
            if self.registration_close_date < self.registration_open_date:
                errors["registration_close_date"] = (
                    "The registration close date must not precede its opening date."
                )
        if categories is None:
            categories = list(
                self.registration_categories.filter(is_active=True).all()
            ) if self.pk else []
        else:
            categories = [category for category in categories if category.is_active]
        if not categories:
            errors["registration_status"] = (
                "At least one active category is required before opening registration."
            )
        for category in categories:
            if category.fee_ngn is None or category.fee_ngn <= 0:
                errors["registration_status"] = (
                    "Every active category must have a positive regular fee."
                )
                break
        if self.early_bird_cutoff_at and any(
            category.early_bird_fee_ngn is None
            for category in categories
        ):
            errors["early_bird_cutoff_at"] = (
                "Configure an early-bird fee for every active category or remove "
                "the edition cutoff."
            )
        if any(
            category.early_bird_fee_ngn is not None
            and (
                self.early_bird_cutoff_at is None
                or category.early_bird_fee_ngn <= 0
                or category.early_bird_fee_ngn >= category.fee_ngn
            )
            for category in categories
        ):
            errors["early_bird_cutoff_at"] = (
                "Early-bird fees must be positive, lower than regular fees, and "
                "have an edition cutoff."
            )
        return errors

    @property
    def pricing_configuration_is_complete(self):
        return not self.pricing_configuration_errors()

    @property
    def pricing_configuration_status(self):
        errors = self.pricing_configuration_errors()
        if errors:
            return "Incomplete: " + "; ".join(errors.values())
        if self.registration_status == self.RegistrationStatus.OPEN:
            return "Open and fully configured"
        return "Ready but closed"


class RegistrationCategory(models.Model):
    class PaymentKind(models.TextChoices):
        PRE_PRIMARY = "pre_primary", "Pre-Primary"
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        UNDERGRADUATE = "undergraduate", "Undergraduates"
        ADULT = "graduate_adult", "Graduates & Adults"

    payment_kind = models.CharField(
        max_length=20, choices=PaymentKind.choices, blank=True, default="",
        help_text="Payment eligibility only; does not change housing, safeguarding or academic allocation.",
    )
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
        null=True,
        blank=True,
        help_text=(
            "Regular fee in NGN. Leave blank until approved. Historical order "
            "quotes and payments retain immutable snapshots."
        ),
    )
    early_bird_fee_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Committee-approved early-bird fee in NGN; never infer a value.",
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
                condition=Q(fee_ngn__isnull=True) | Q(fee_ngn__gte=0),
                name="dic_category_fee_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(early_bird_fee_ngn__isnull=True)
                | Q(early_bird_fee_ngn__gte=0),
                name="dic_category_early_bird_fee_nonnegative",
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
        errors = {}
        if (
            self.minimum_age is not None
            and self.maximum_age is not None
            and self.maximum_age < self.minimum_age
        ):
            errors["maximum_age"] = "Maximum age must not be less than minimum age."
        tutor_category = self.name == 'DIC Tutor' or (self.pk and self.registration_items.filter(order__registration_basis='tutor').exists())
        if tutor_category and (self.is_active or self.fee_ngn != 0):
            errors['is_active'] = 'Internal tutor category must remain inactive with zero amount due.'
        if self.early_bird_fee_ngn is not None:
            if self.fee_ngn is None or self.early_bird_fee_ngn >= self.fee_ngn:
                errors["early_bird_fee_ngn"] = (
                    "An early-bird fee must be lower than a configured regular fee."
                )
            if self.early_bird_fee_ngn <= 0:
                errors["early_bird_fee_ngn"] = "The early-bird fee must be positive."
        if (self.pk and self.registration_items.exists()
                and type(self).objects.filter(pk=self.pk).exclude(edition_id=self.edition_id).exists()):
            errors["edition"] = "A category referenced by registrations cannot change edition."
        if errors:
            raise ValidationError(errors)

    def current_price(self, at=None):
        at = at or timezone.now()
        cutoff = self.edition.early_bird_cutoff_at
        if (
            self.early_bird_fee_ngn is not None
            and cutoff is not None
            and at < cutoff
        ):
            return self.early_bird_fee_ngn, "early_bird"
        return self.fee_ngn, "regular"


class House(models.Model):
    badge_colour = models.CharField(max_length=7, blank=True,
        validators=[RegexValidator(
            r'^#[0-9A-Fa-f]{6}$', 'Use a six-digit hex colour, for example #174a34.')],
        help_text='Committee-approved badge colour. Leave blank until approved.')
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
    reserve_authorized_at = models.DateTimeField(null=True, blank=True)
    reserve_authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="authorized_dic_reserve_houses",
        null=True,
        blank=True,
    )
    reserve_authorization_reason = models.TextField(blank=True)
    reserve_designation = models.BooleanField(default=False, editable=False)
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
                condition=(~Q(status='active') | Q(reserve_designation=False)) & (~Q(status='reserve') | Q(reserve_designation=True)),
                name='dic_reserve_designation_safe',
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
        from .house_configuration import house_capacity_limit
        limit = house_capacity_limit(self.edition)
        if self.capacity is not None and self.capacity > limit:
            errors['capacity'] = f'No house may have a capacity above {limit} occupants for this edition.'
        if self.status == self.Status.RESERVE:
            self.reserve_designation = True
        if self.reserve_designation and self.status == self.Status.ACTIVE:
            errors['status'] = 'Reserve houses retain Reserve status; use explicit reserve authorization.'
        if self.pk:
            occupied = self.allocations.filter(
                status=HouseAllocation.Status.ALLOCATED
            ).count()
            previous = type(self).objects.filter(pk=self.pk).first()
            if occupied and previous and any(getattr(previous, key) != getattr(self, key)
                    for key in ('edition_id', 'gender', 'purpose', 'status')):
                errors['status'] = 'Release or reassign occupants before changing house designation, edition, purpose or status.'
            if self.capacity is not None and occupied > self.capacity:
                errors["capacity"] = (
                    "Capacity cannot be reduced below the current active occupancy."
                )
            if self.status == self.Status.INACTIVE and occupied:
                errors["status"] = (
                    "Release or reassign active allocations before deactivating this house."
                )

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

    def save(self, *args, **kwargs):
        with transaction.atomic():
            CampEdition.objects.select_for_update().get(pk=self.edition_id)
            if self.pk and type(self).objects.filter(pk=self.pk, reserve_designation=True).exists():
                self.reserve_designation = True
            if self.status == self.Status.RESERVE:
                self.reserve_designation = True
            self.clean()
            if kwargs.get('update_fields'):
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'reserve_designation'}
            super().save(*args, **kwargs)


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
        NOT_APPLICABLE = "None", "None (Not applicable)"

    class MaritalStatus(models.TextChoices):
        SINGLE = "Single", "Single"
        MARRIED = "Married", "Married"
        DIVORCEE = "Divorcee", "Divorcee"
        WIDOW_WIDOWER = "Widow / Widower", "Widow / Widower"
        NOT_APPLICABLE = "None", "None (Not applicable)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200)
    address = models.TextField()
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    date_of_birth = models.DateField(null=True, blank=True)
    age_declaration = models.CharField(max_length=5, default='exact', choices=[
        ('exact', 'Exact date of birth'), ('minor', 'Minor (under 18)'), ('adult', 'Adult (18+)')])
    adult_declared_on = models.DateField(null=True, blank=True, editable=False)
    sex = models.CharField(max_length=6, choices=Sex.choices)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    academic_status = models.CharField(max_length=50, choices=AcademicStatus.choices)
    occupation = models.CharField(max_length=32, choices=Occupation.choices)
    marital_status = models.CharField(max_length=20, choices=MaritalStatus.choices)
    eligible_for_dedicated_accommodation = models.BooleanField(
        default=False,
        help_text=(
            "Must be explicitly set by an authorised administrator; eligibility "
            "is never inferred from participant details."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        permissions = [
            (
                "can_authorize_dedicated_accommodation",
                "Can authorize participants for dedicated accommodation",
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(age_declaration__in=['exact', 'minor', 'adult']), name='dic_participant_age_declaration'),
            models.CheckConstraint(condition=(Q(date_of_birth__isnull=False, adult_declared_on__isnull=True)
                | Q(date_of_birth__isnull=True, age_declaration='adult', adult_declared_on__isnull=False)),
                name='dic_participant_age_evidence'),
            models.CheckConstraint(
                condition=Q(height_cm__gt=0),
                name="dic_participant_height_positive",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__gt=0),
                name="dic_participant_weight_positive",
            ),
        ]

    def clean(self):
        super().clean()
        from .registration_age import validate_declaration
        validate_declaration(self.age_declaration, self.date_of_birth, timezone.localdate())
        if self.date_of_birth is None:
            if self.adult_declared_on is None:
                self.adult_declared_on = timezone.localdate()
            if self.adult_declared_on > timezone.localdate():
                from django.core.exceptions import ValidationError
                raise ValidationError('Adult declaration date cannot be in the future.')
        else:
            self.adult_declared_on = None

    def __str__(self):
        return self.full_name


class RegistrationOrder(models.Model):
    registration_basis = models.CharField(max_length=16, default='paid', choices=[('paid', 'Paid registration'), ('tutor', 'Complimentary tutor')])
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required (authorized tutor)"
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
    current_price_revision = models.ForeignKey(
        "RegistrationOrderPriceRevision",
        on_delete=models.PROTECT,
        related_name="current_for_orders",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    payment_status = models.CharField(
        max_length=12,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    idempotency_key_digest = models.CharField(max_length=64, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    access_token_digest = models.CharField(max_length=64)
    access_token_expires_at = models.DateTimeField(
        default=order_access_token_expiry,
    )
    access_token_revoked_at = models.DateTimeField(null=True, blank=True)
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
                    payment_status__in=("pending", "paid", "failed", "refunded", "not_required")
                ),
                name="dic_order_payment_status_valid",
            ),
            models.CheckConstraint(condition=(Q(registration_basis='paid') & ~Q(payment_status='not_required')) | Q(registration_basis='tutor', payment_status='not_required', current_price_revision__isnull=True), name='dic_order_registration_basis'),
        ]

    def __str__(self):
        return f"Order {self.public_id}"

    @property
    def total_amount_ngn(self):
        if self.current_price_revision_id:
            return self.current_price_revision.total_amount_ngn
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
                if self.fee_snapshot_ngn is None:
                    self.fee_snapshot_ngn = self.category.fee_ngn
            if self.participant_id:
                participant = self.participant
                self.participant_snapshot = {
                    "full_name": participant.full_name,
                    "address": participant.address,
                    "phone": participant.phone,
                    "email": participant.email,
                    "date_of_birth": participant.date_of_birth.isoformat() if participant.date_of_birth else None,
                    "sex": participant.sex,
                    "height_cm": str(participant.height_cm) if participant.height_cm is not None else None,
                    "weight_kg": str(participant.weight_kg) if participant.weight_kg is not None else None,
                    "academic_status": participant.academic_status,
                    "occupation": participant.occupation,
                    "marital_status": participant.marital_status,
                }
                if participant.age_declaration != 'exact':
                    self.participant_snapshot.update(
                        age_declaration=participant.age_declaration,
                        adult_declared_on=participant.adult_declared_on.isoformat() if participant.adult_declared_on else None)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registration order items cannot be deleted.")


class RegistrationOrderPriceRevision(models.Model):
    order = models.ForeignKey(
        RegistrationOrder,
        on_delete=models.PROTECT,
        related_name="price_revisions",
    )
    revision_number = models.PositiveSmallIntegerField()
    early_bird_cutoff_at = models.DateTimeField(null=True, blank=True)
    total_amount_ngn = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("revision_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "revision_number"),
                name="dic_order_price_revision_unique",
            ),
            models.CheckConstraint(
                condition=Q(total_amount_ngn__gte=0),
                name="dic_order_price_revision_total_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.order} — price revision {self.revision_number}"

    def save(self, *args, **kwargs):
        if self.order.registration_basis != 'paid':
            raise ValidationError('Tutor registrations cannot have payment price revisions.')
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values().first()
            if previous and any(
                previous[field] != getattr(self, field)
                for field in (
                    "order_id",
                    "revision_number",
                    "early_bird_cutoff_at",
                    "total_amount_ngn",
                    "created_at",
                )
            ):
                raise ValidationError("Price revision details are immutable.")
            if (
                previous
                and previous["accepted_at"] is not None
                and previous["accepted_at"] != self.accepted_at
            ):
                raise ValidationError("Accepted price revisions cannot be reopened.")
        super().save(*args, **kwargs)


class RegistrationOrderPriceItem(models.Model):
    class PriceType(models.TextChoices):
        EARLY_BIRD = "early_bird", "Early bird"
        REGULAR = "regular", "Regular"

    revision = models.ForeignKey(
        RegistrationOrderPriceRevision,
        on_delete=models.PROTECT,
        related_name="items",
    )
    order_item = models.ForeignKey(
        RegistrationOrderItem,
        on_delete=models.PROTECT,
        related_name="price_revision_items",
    )
    category_name_snapshot = models.CharField(max_length=120)
    early_bird_fee_snapshot_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    regular_fee_snapshot_ngn = models.DecimalField(max_digits=12, decimal_places=2)
    fee_snapshot_ngn = models.DecimalField(max_digits=12, decimal_places=2)
    price_type = models.CharField(max_length=10, choices=PriceType.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "order_item"),
                name="dic_price_revision_order_item_unique",
            ),
            models.CheckConstraint(
                condition=Q(fee_snapshot_ngn__gte=0),
                name="dic_price_revision_item_fee_nonnegative",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values().first()
            if previous and any(
                previous[field] != getattr(self, field)
                for field in (
                    "revision_id",
                    "order_item_id",
                    "category_name_snapshot",
                    "early_bird_fee_snapshot_ngn",
                    "regular_fee_snapshot_ngn",
                    "fee_snapshot_ngn",
                    "price_type",
                )
            ):
                raise ValidationError("Price revision line items are immutable.")
        super().save(*args, **kwargs)


class HouseAllocation(models.Model):
    class Status(models.TextChoices):
        ALLOCATED = "allocated", "Allocated"
        REASSIGNED = "reassigned", "Reassigned"
        RELEASED = "released", "Released"

    class Source(models.TextChoices):
        ADMIN = "admin", "Administrator"
        SYSTEM = "system", "Allocation process"

    participant = models.ForeignKey(
        Participant,
        on_delete=models.PROTECT,
        related_name="house_allocations",
    )
    edition = models.ForeignKey(
        CampEdition,
        on_delete=models.PROTECT,
        related_name="house_allocations",
    )
    house = models.ForeignKey(
        House,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ALLOCATED,
    )
    allocated_at = models.DateTimeField(default=timezone.now)
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="dic_house_allocations",
        null=True,
        blank=True,
    )
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="released_dic_house_allocations",
        null=True,
        blank=True,
    )
    source = models.CharField(
        max_length=8,
        choices=Source.choices,
        default=Source.ADMIN,
    )
    previous_allocation = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="subsequent_allocations",
        null=True,
        blank=True,
    )
    change_reason = models.TextField(blank=True)
    resolution_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("-allocated_at", "-pk")
        permissions = [
            ("can_allocate_participants", "Can allocate DIC participants"),
            ("can_reassign_allocations", "Can reassign DIC house allocations"),
            ("can_release_allocations", "Can release DIC house allocations"),
            ("can_activate_reserve_houses", "Can authorize DIC reserve houses"),
            ("can_approve_allocation_strategy", "Can approve DIC allocation strategies"),
            ("can_verify_venue_directions", "Can verify DIC venue directions"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("participant", "edition"),
                condition=Q(status="allocated"),
                name="dic_one_active_house_allocation",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("allocated", "reassigned", "released")),
                name="dic_house_allocation_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.participant} — {self.house} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        errors = {}
        if self.edition_id and self.house_id and self.house.edition_id != self.edition_id:
            errors["house"] = "The house must belong to the allocation edition."
        from .tutor_registration import is_tutor
        if self.participant_id and self.edition_id and is_tutor(self.participant_id, self.edition_id):
            errors['participant'] = 'Tutor accommodation is managed offline; camper housing is unavailable.'
        if self.participant_id and self.edition_id:
            paid_order_exists = RegistrationOrderItem.objects.filter(
                participant_id=self.participant_id,
                order__edition_id=self.edition_id,
                order__payment_status=RegistrationOrder.PaymentStatus.PAID,
                order__status=RegistrationOrder.Status.CONFIRMED,
                order__payment_attempts__status=PaymentAttempt.Status.SUCCESSFUL,
            ).exclude(order__status=RegistrationOrder.Status.CANCELLED).exists()
            if not paid_order_exists:
                errors["participant"] = (
                    "Only participants on a paid order for this edition can be allocated."
                )
        if self.previous_allocation_id and self.participant_id and self.edition_id:
            previous = self.previous_allocation
            if (
                previous.participant_id != self.participant_id
                or previous.edition_id != self.edition_id
            ):
                errors["previous_allocation"] = (
                    "Allocation history must belong to the same participant and edition."
                )
        if self.participant_id and self.house_id and self.edition_id and self.status == self.Status.ALLOCATED:
            from .housing_policy import validate_occupant
            try:
                validate_occupant(self.participant, self.edition, self.house)
            except ValidationError as exc:
                errors['house'] = exc.messages
        if (
            self.house_id
            and self.house.purpose == House.Purpose.FATHERS_AND_ADMINS
            and not self.participant.eligible_for_dedicated_accommodation
        ):
            errors["house"] = (
                "Dedicated accommodation requires explicit administrator-approved "
                "participant eligibility."
            )
        if (
            self.house_id
            and self.house.status == House.Status.INACTIVE
            and self.status == self.Status.ALLOCATED
        ):
            errors["house"] = "Participants cannot be allocated to an inactive house."
        if (
            self.house_id
            and self.house.status == House.Status.RESERVE
            and not self.house.reserve_authorized_at
            and self.status == self.Status.ALLOCATED
        ):
            errors["house"] = "The reserve house has not been authorised for use."
        if self.house_id and self.house.eligibility_rules and self.status == self.Status.ALLOCATED:
            errors["house"] = (
                "This house has eligibility rules without an approved evaluator; "
                "allocation is blocked."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding and self.pk is None and self.status == self.Status.ALLOCATED:
            with transaction.atomic():
                CampEdition.objects.select_for_update().get(pk=self.edition_id)
                self.clean()
                capacity = self.house.capacity
                from .house_configuration import house_capacity_limit
                limit = house_capacity_limit(self.edition)
                if capacity is None or capacity > limit:
                    raise ValidationError(f'A confirmed capacity of at most {limit} is required.')
                occupied = type(self).objects.filter(house_id=self.house_id, status='allocated').count()
                if occupied >= capacity:
                    raise ValidationError('House has reached its configured capacity.')
                super().save(*args, **kwargs)
            return
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "participant_id",
                "edition_id",
                "house_id",
                "allocated_at",
                "allocated_by_id",
                "source",
                "previous_allocation_id",
                "status",
            ).first()
            if previous:
                immutable_fields = (
                    "participant_id",
                    "edition_id",
                    "house_id",
                    "allocated_at",
                    "allocated_by_id",
                    "source",
                    "previous_allocation_id",
                )
                if any(previous[field] != getattr(self, field) for field in immutable_fields):
                    raise ValidationError(
                        "Allocation identity and assignment details are immutable; "
                        "create a reassignment record instead."
                    )
                if previous["status"] != self.Status.ALLOCATED and previous["status"] != self.status:
                    raise ValidationError("Allocation history records cannot be reopened.")
                if (
                    previous["status"] == self.Status.ALLOCATED
                    and self.status
                    not in (self.Status.ALLOCATED, self.Status.REASSIGNED, self.Status.RELEASED)
                ):
                    raise ValidationError("Invalid allocation status transition.")
        super().save(*args, **kwargs)


class PaymentAttempt(models.Model):
    class Status(models.TextChoices):
        INITIALIZING = "initializing", "Initializing"
        PENDING = "pending", "Pending"
        INITIALIZATION_UNKNOWN = "init_unknown", "Initialization unknown"
        VERIFICATION_PENDING = "verify_pending", "Verification pending"
        FAILED = "failed", "Failed"
        AMOUNT_MISMATCH = "amount_mismatch", "Amount mismatch"
        SUPERSEDED = "superseded", "Superseded quote"
        RECONCILIATION_REQUIRED = "reconcile", "Reconciliation required"
        SUCCESSFUL = "successful", "Successful"
        DUPLICATE_SUCCESS = "duplicate_success", "Duplicate successful charge"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        RegistrationOrder,
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    price_revision = models.ForeignKey(
        RegistrationOrderPriceRevision,
        on_delete=models.PROTECT,
        related_name="payment_attempts",
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=80, unique=True)
    provider_mode = models.CharField(max_length=4, choices=[('test', 'Test'), ('live', 'Live')], default='test', editable=False)
    amount_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIALIZING,
    )
    authorization_url = models.URLField(max_length=500, blank=True)
    provider_transaction_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
    )
    provider_status = models.CharField(max_length=32, blank=True)
    provider_reported_amount_kobo = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )
    provider_reported_currency = models.CharField(max_length=16, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    provider_paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_kobo__gt=0),
                name="dic_payment_attempt_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(currency="NGN"),
                name="dic_payment_attempt_currency_ngn",
            ),
            models.UniqueConstraint(
                fields=("order",),
                condition=Q(
                    status__in=(
                        "initializing",
                        "pending",
                        "init_unknown",
                        "verify_pending",
                        "amount_mismatch",
                        "reconcile",
                    )
                ),
                name="dic_one_unresolved_payment_per_order",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.order.registration_basis != 'paid':
            raise ValidationError('Tutor registrations cannot have payment attempts.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} — {self.status}"


class PaymentReturnGrant(models.Model):
    """Short-lived browser-session authority; never stores raw order tokens."""
    order = models.ForeignKey(RegistrationOrder, on_delete=models.CASCADE, related_name="return_grants")
    session_digest = models.CharField(max_length=64, db_index=True)
    access_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("order", "session_digest"), name="dic_return_grant_order_session_unique")]


class PaystackWebhookEvent(models.Model):
    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        RETRY = "retry", "Retry required"

    id = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=80)
    reference = models.CharField(max_length=80, blank=True)
    payload_digest = models.CharField(max_length=64, unique=True)
    processing_status = models.CharField(
        max_length=12,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
    )
    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="webhook_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.event_type} — {self.processing_status}"


class RegistrationRecoveryChallenge(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class DeliveryStatus(models.TextChoices):
        NOT_SENT = "not_sent", "Not sent"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SUPPRESSED = "suppressed", "Suppressed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact_digest = models.CharField(max_length=64, db_index=True)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    code_digest = models.CharField(max_length=64)
    encrypted_delivery_payload = models.TextField(blank=True)
    orders = models.ManyToManyField(
        RegistrationOrder,
        related_name="recovery_challenges",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    resend_after = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    delivery_started_at = models.DateTimeField(null=True, blank=True)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    delivery_status = models.CharField(
        max_length=10,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.QUEUED,
    )

    class Meta:
        indexes = [
            models.Index(fields=("contact_digest", "channel", "created_at")),
            models.Index(fields=("expires_at", "consumed_at")),
        ]


class RegistrationRecoveryGrant(models.Model):
    token_digest = models.CharField(max_length=64, unique=True)
    challenge = models.ForeignKey(
        RegistrationRecoveryChallenge,
        on_delete=models.CASCADE,
        related_name="grants",
    )
    orders = models.ManyToManyField(
        RegistrationOrder,
        related_name="recovery_grants",
        blank=True,
        through="RegistrationRecoveryGrantOrder",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("expires_at", "revoked_at"))]


class RegistrationRecoveryGrantOrder(models.Model):
    grant = models.ForeignKey(
        RegistrationRecoveryGrant,
        on_delete=models.CASCADE,
        related_name="order_grants",
    )
    order = models.ForeignKey(
        RegistrationOrder,
        on_delete=models.CASCADE,
        related_name="recovery_order_grants",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("grant", "order"),
                name="dic_recovery_grant_order_unique",
            )
        ]


class RegistrationRecoveryRateLimit(models.Model):
    key_digest = models.CharField(max_length=64, unique=True)
    window_started_at = models.DateTimeField()
    request_count = models.PositiveSmallIntegerField(default=0)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DICAdminAuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="dic_admin_audit_events",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("target_type", "target_id")),
        ]

    def __str__(self):
        return f"{self.action} — {self.target_type} {self.target_id}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("DIC administrative audit events are immutable.")
        if not isinstance(self.details, dict):
            raise ValidationError({"details": "Audit details must be a JSON object."})
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("DIC administrative audit events cannot be deleted.")


class CampEnrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name="enrollments")
    edition = models.ForeignKey(CampEdition, on_delete=models.PROTECT, related_name="enrollments")
    source_item = models.ForeignKey(RegistrationOrderItem, on_delete=models.PROTECT, related_name="enrollments")
    participant_number = models.CharField(max_length=32, unique=True, editable=False)
    source_review_fingerprint = models.CharField(max_length=64, blank=True)
    restriction_reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    portrait = models.FileField(storage=private_participant_storage, validators=[validate_photo], max_length=200, blank=True,
        help_text='Optional approved participant portrait, stored privately.')

    class Meta:
        constraints = [models.UniqueConstraint(fields=("participant", "edition"), name="dic_enrollment_participant_edition_unique")]
        permissions = [
            ("can_view_dic_ids", "Can look up DIC participant IDs"),
            ("can_manage_dic_ids", "Can issue and revoke DIC participant IDs"),
            ("can_review_dic_enrollment_sources", "Can resolve DIC enrollment sources and restrictions"),
        ]

    def __str__(self):
        return self.participant_number

    def clean(self):
        super().clean()
        if self.source_item_id and (self.source_item.participant_id != self.participant_id or self.source_item.order.edition_id != self.edition_id or self.source_item.category.edition_id != self.edition_id):
            raise ValidationError("Enrollment source must belong to the participant and edition.")


class HouseScoreTransaction(models.Model):
    """Append-only points ledger; corrections are opposing transactions."""
    edition = models.ForeignKey(CampEdition, on_delete=models.PROTECT, related_name='score_transactions')
    house = models.ForeignKey(House, on_delete=models.PROTECT, related_name='score_transactions')
    entry_type = models.CharField(max_length=9, choices=[('award', 'Award'), ('deduction', 'Deduction')])
    points = models.PositiveIntegerField()
    activity = models.CharField(max_length=200)
    note = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='dic_score_transactions', editable=False)
    request_id = models.UUIDField(editable=False)
    reverses = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reversal', editable=False)

    class Meta:
        default_permissions = ()
        permissions = [
            ('can_view_dic_scores', 'Can view DIC house scores'),
            ('can_record_dic_scores', 'Can award and deduct DIC house points'),
            ('can_correct_dic_scores', 'Can reverse DIC scoring errors'),
        ]
        constraints = [
            models.UniqueConstraint(fields=('edition', 'request_id'), name='dic_score_edition_request_unique'),
            models.CheckConstraint(condition=Q(points__gte=1, points__lte=2147483647), name='dic_score_positive_points'),
            models.CheckConstraint(condition=Q(entry_type__in=('award', 'deduction')), name='dic_score_entry_type_valid'),
        ]


class CampCheckIn(models.Model):
    """One physical arrival per participant/edition; not daily attendance."""
    participant = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name='camp_check_ins')
    edition = models.ForeignKey(CampEdition, on_delete=models.PROTECT, related_name='check_ins')
    checked_in_at = models.DateTimeField(default=timezone.now, editable=False)
    checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='dic_check_ins', editable=False)

    class Meta:
        default_permissions = ()
        permissions = [('can_check_in_dic_participants', 'Can check in DIC participants')]
        constraints = [models.UniqueConstraint(fields=('participant', 'edition'), name='dic_checkin_participant_edition_unique')]


class ParticipantPortalChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(RegistrationOrder, null=True, on_delete=models.PROTECT)
    channel = models.CharField(max_length=10)
    contact_digest = models.CharField(max_length=64, db_index=True)
    browser_digest = models.CharField(max_length=64)
    code_digest = models.CharField(max_length=64)
    encrypted_delivery_payload = models.TextField(blank=True)
    delivery_status = models.CharField(max_length=12, default="queued", choices=RegistrationRecoveryChallenge.DeliveryStatus.choices)
    delivery_started_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)


class ParticipantPortalGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credential_digest = models.CharField(max_length=64, unique=True)
    channel = models.CharField(max_length=10)
    contact_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True)


class ParticipantPortalScope(models.Model):
    grant = models.ForeignKey(ParticipantPortalGrant, on_delete=models.CASCADE, related_name="scopes")
    order = models.ForeignKey(RegistrationOrder, on_delete=models.PROTECT)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("grant", "order"), name="dic_portal_grant_order_unique")]


class DigitalIDIssue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(CampEnrollment, on_delete=models.PROTECT, related_name="id_issues")
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="dic_id_issues")
    revoked_at = models.DateTimeField(null=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="dic_id_revocations")
    reason = models.CharField(max_length=240, blank=True)
    verification_digest = models.CharField(max_length=64, null=True, unique=True, editable=False)
    verification_secret = models.TextField(blank=True, editable=False)

    def save(self, *args, issuance_actor=None, **kwargs):
        from .participant_services import require_id_manager, eligibility
        if self._state.adding:
            require_id_manager(issuance_actor)
            if self.issued_by_id != issuance_actor.pk or not self.verification_digest or not self.verification_secret:
                raise ValidationError('Use the authorized ID issuance service.')
            if not eligibility(self.enrollment)['eligible']:
                raise ValidationError('Verified payment eligibility is required for issuance.')
        else:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ('enrollment_id', 'version', 'issued_by_id', 'expires_at')
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Issued identity fields are immutable; authorize a replacement.')
            if (previous.verification_digest, previous.verification_secret) != (self.verification_digest, self.verification_secret):
                require_id_manager(issuance_actor)
                if previous.verification_digest or self.revoked_at or self.expires_at <= timezone.now() or not eligibility(self.enrollment)['eligible']:
                    raise ValidationError('Only an eligible active legacy credential may be activated; otherwise reissue.')
            if (previous.revoked_at, previous.revoked_by_id) != (self.revoked_at, self.revoked_by_id):
                # Source-review staff retain their existing right to invalidate
                # credentials when restricting or correcting an enrollment.
                if not (issuance_actor and issuance_actor.is_authenticated and issuance_actor.is_active
                        and issuance_actor.is_staff and (issuance_actor.has_perm('dic.can_manage_dic_ids')
                        or issuance_actor.has_perm('dic.can_review_dic_enrollment_sources'))):
                    require_id_manager(issuance_actor)
                if previous.revoked_at or not self.revoked_at or self.revoked_by_id != issuance_actor.pk:
                    raise ValidationError('Revocation is permanent and requires the responsible staff account.')
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("enrollment", "version"), name="dic_id_issue_version_unique"),
            models.UniqueConstraint(fields=("enrollment",), condition=Q(revoked_at__isnull=True), name="dic_one_current_id_issue"),
            models.CheckConstraint(condition=Q(version__gte=1), name="dic_id_version_positive"),
        ]


# Public camp content is independent of registration and participant records.
from .memory_models import CampPhotograph, MemoryActivity, CampVideo  # noqa: E402,F401

from .showcase_models import Lecturer, LecturerAppearance, CampActivity  # noqa: E402,F401

from .promo_models import PromoVideo, CampFlyer  # noqa: E402,F401
from .housing_models import GuardianRelationship, HousingJob  # noqa: E402,F401
from .feedback_models import AnonymousCamperResponse, CamperFeedbackReceipt, LecturerFeedbackAccess, IdentifiedFeedback, WelfareReport, WelfareEvent  # noqa: E402,F401
from .tutor_models import TutorRegistrationAuthorization, TutorVerification  # noqa: E402,F401
from .portal_account_models import PortalAccount, PortalAccountBooking, PortalAccountSession, PortalGoogleLink, PortalOAuthAttempt, PortalCredentialTransition  # noqa: E402,F401
from .timetable_models import TimetableEntry  # noqa: E402,F401
from .launch_models import AcademicClass, AcademicAssignment, CampAnnouncement  # noqa: E402,F401
from .foundation_models import ContactEnquiry, FoundationDonation  # noqa: E402,F401

from .fulfillment_models import CamperFulfillmentJob  # noqa: E402,F401
from .order_lifecycle_models import OrderExpiryPolicy, OrderExpiry, PaymentResolution  # noqa: E402,F401
