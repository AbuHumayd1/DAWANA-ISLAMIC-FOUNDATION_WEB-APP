from decimal import Decimal
from urllib.parse import quote

from django.utils import timezone
from rest_framework import serializers

from .models import (
    CampEdition,
    LAGOS_TIME_ZONE,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)
from .pricing import PricingConfigurationError, price_for_category


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unexpected = set(data.keys()) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError(
                    {
                        key: ["Unexpected field."]
                        for key in sorted(unexpected)
                    }
                )
        return super().to_internal_value(data)


class RegistrationCategoryOptionSerializer(serializers.ModelSerializer):
    regular_fee_ngn = serializers.DecimalField(
        source="fee_ngn",
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        read_only=True,
    )
    early_bird_fee_ngn = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        read_only=True,
    )
    current_price_type = serializers.SerializerMethodField()
    current_fee_ngn = serializers.SerializerMethodField()
    early_bird_cutoff_at = serializers.DateTimeField(
        source="edition.early_bird_cutoff_at",
        allow_null=True,
        read_only=True,
    )

    class Meta:
        model = RegistrationCategory
        fields = (
            "id",
            "name",
            "description",
            "payment_kind",
            "minimum_age",
            "maximum_age",
            "fee_ngn",
            "regular_fee_ngn",
            "early_bird_fee_ngn",
            "current_price_type",
            "current_fee_ngn",
            "early_bird_cutoff_at",
        )

    def get_current_price_type(self, category):
        try:
            return price_for_category(category, timezone.now())["price_type"]
        except PricingConfigurationError:
            return None

    def get_current_fee_ngn(self, category):
        try:
            return price_for_category(category, timezone.now())["fee_ngn"]
        except PricingConfigurationError:
            return None


class ActiveEditionSerializer(serializers.ModelSerializer):
    registration_is_open = serializers.SerializerMethodField()
    registration_configuration_status = serializers.CharField(
        source="pricing_configuration_status",
        read_only=True,
    )
    categories = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    venue_directions_url = serializers.SerializerMethodField()
    early_bird_cutoff_at_lagos = serializers.SerializerMethodField()

    class Meta:
        model = CampEdition
        fields = (
            "id",
            "name",
            "year",
            "camp_start_date",
            "housing_age_reference_date",
            "camp_end_date",
            "registration_open_date",
            "registration_close_date",
            "registration_status",
            "registration_is_open",
            "registration_configuration_status",
            "venue",
            "venue_directions_url",
            "early_bird_cutoff_at",
            "early_bird_cutoff_at_lagos",
            "venue_directions_verified",
            "general_information",
            "categories",
        )

    def get_registration_is_open(self, edition):
        today = timezone.localdate()
        return (
            edition.registration_status == CampEdition.RegistrationStatus.OPEN
            and edition.registration_open_date is not None
            and edition.registration_close_date is not None
            and edition.registration_open_date <= today <= edition.registration_close_date
            and edition.pricing_configuration_is_complete
        )

    def get_categories(self, edition):
        return RegistrationCategoryOptionSerializer(
            edition.registration_categories.all(),
            many=True,
        ).data

    def get_venue(self, edition):
        return edition.venue_name or edition.general_information.get("venue", "")

    def get_venue_directions_url(self, edition):
        if not (
            edition.venue_directions_verified
            and edition.venue_directions_verified_at
            and edition.venue_directions_verified_by_id
        ):
            return None
        if edition.venue_directions_address:
            destination = quote(edition.venue_directions_address, safe="")
            return f"https://www.google.com/maps/dir/?api=1&destination={destination}"
        if edition.venue_google_place_id:
            name = quote(edition.venue_name, safe="")
            place_id = quote(edition.venue_google_place_id, safe="")
            return (
                "https://www.google.com/maps/dir/?api=1"
                f"&destination={name}&destination_place_id={place_id}"
            )
        if edition.venue_latitude is not None and edition.venue_longitude is not None:
            destination = quote(
                f"{edition.venue_latitude},{edition.venue_longitude}",
                safe=",",
            )
            return f"https://www.google.com/maps/dir/?api=1&destination={destination}"
        return None

    def get_early_bird_cutoff_at_lagos(self, edition):
        if edition.early_bird_cutoff_at is None:
            return None
        return timezone.localtime(
            edition.early_bird_cutoff_at,
            LAGOS_TIME_ZONE,
        ).isoformat()


class PrimaryRegistrantInputSerializer(StrictSerializer):
    full_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField()

    def validate_email(self, value):
        from .recovery import normalize_email
        return normalize_email(value)


class ParticipantInputSerializer(StrictSerializer):
    category_id = serializers.IntegerField(min_value=1)
    full_name = serializers.CharField(max_length=200)
    address = serializers.CharField()
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField()
    date_of_birth = serializers.DateField(required=False, allow_null=True, default=None)
    age_declaration = serializers.ChoiceField(choices=['exact', 'minor', 'adult'], required=False, default='exact')
    sex = serializers.ChoiceField(choices=Participant.Sex.choices)
    height_cm = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False, allow_null=True, default=None,
    )
    weight_kg = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False, allow_null=True, default=None,
    )
    academic_status = serializers.ChoiceField(
        choices=Participant.AcademicStatus.choices
    )
    occupation = serializers.ChoiceField(choices=Participant.Occupation.choices)
    marital_status = serializers.ChoiceField(
        choices=Participant.MaritalStatus.choices
    )

    def validate_date_of_birth(self, value):
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate(self, attrs):
        from .registration_age import validate_declaration
        from django.core.exceptions import ValidationError as AgeError
        try:
            validate_declaration(attrs['age_declaration'], attrs['date_of_birth'], timezone.localdate())
        except AgeError as error:
            raise serializers.ValidationError({'date_of_birth': error.messages})
        return attrs


class RegistrationCredentialsSerializer(StrictSerializer):
    username = serializers.CharField(min_length=3, max_length=40, write_only=True)

    def validate_username(self, value):
        from .portal_accounts import normalize_username
        return normalize_username(value)

    password = serializers.CharField(min_length=12, max_length=128, trim_whitespace=False, write_only=True)
    password_confirmation = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, data):
        import secrets
        if not secrets.compare_digest(data['password'].encode(), data['password_confirmation'].encode()):
            raise serializers.ValidationError({'password_confirmation': 'Passwords must match.'})
        from django.contrib.auth import get_user_model
        from .portal_accounts import password_policy
        password_policy(data['password'], get_user_model()(username=data['username']))
        data.pop('password_confirmation')
        return data


class GuardianDeclarationSerializer(StrictSerializer):
    child_index = serializers.IntegerField(min_value=0)
    guardian_index = serializers.IntegerField(min_value=0)
    confirmed = serializers.BooleanField()


class RegistrationOrderCreateSerializer(StrictSerializer):
    portal_account = RegistrationCredentialsSerializer(write_only=True)
    primary_registrant = PrimaryRegistrantInputSerializer()
    participants = ParticipantInputSerializer(many=True, allow_empty=False)
    guardian_relationships = GuardianDeclarationSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        participants = attrs['participants']
        seen = set()
        for relation in attrs['guardian_relationships']:
            child, guardian = relation['child_index'], relation['guardian_index']
            if (not relation['confirmed'] or child == guardian or child in seen
                    or child >= len(participants) or guardian >= len(participants)):
                raise serializers.ValidationError('Confirm one distinct guardian in this booking for each dependent child.')
            seen.add(child)
        return attrs


class PrimaryRegistrantReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrimaryRegistrant
        fields = ("full_name", "phone", "email")


class RegistrationOrderItemReadSerializer(serializers.ModelSerializer):
    participant_id = serializers.UUIDField(read_only=True)
    category_id = serializers.IntegerField(read_only=True)
    current_fee_ngn = serializers.SerializerMethodField()
    current_price_type = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationOrderItem
        fields = (
            "participant_id",
            "category_id",
            "category_name_snapshot",
            "fee_snapshot_ngn",
            "current_fee_ngn",
            "current_price_type",
            "participant_snapshot",
        )

    def _current_price_item(self, item):
        return self.context.get("current_price_items", {}).get(item.pk)

    def get_current_fee_ngn(self, item):
        price_item = self._current_price_item(item)
        return (
            price_item.fee_snapshot_ngn
            if price_item
            else item.fee_snapshot_ngn
        )

    def get_current_price_type(self, item):
        price_item = self._current_price_item(item)
        return price_item.price_type if price_item else "regular"


class RegistrationOrderReadSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="public_id", read_only=True)
    edition_name = serializers.CharField(source="edition.name", read_only=True)
    primary_registrant = PrimaryRegistrantReadSerializer(read_only=True)
    total_amount_ngn = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    items = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationOrder
        fields = (
            "order_id",
            "edition_name",
            "status",
            "payment_status",
            "registration_basis",
            "total_amount_ngn",
            "created_at",
            "submitted_at",
            "primary_registrant",
            "items",
        )

    def get_items(self, order):
        current_price_items = {}
        if order.current_price_revision_id:
            current_price_items = {
                price_item.order_item_id: price_item
                for price_item in order.current_price_revision.items.all()
            }
        return RegistrationOrderItemReadSerializer(
            order.items.all(),
            many=True,
            context={
                **self.context,
                "current_price_items": current_price_items,
            },
        ).data
