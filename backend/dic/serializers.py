from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import (
    CampEdition,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
)


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
    class Meta:
        model = RegistrationCategory
        fields = (
            "id",
            "name",
            "description",
            "minimum_age",
            "maximum_age",
            "fee_ngn",
        )


class ActiveEditionSerializer(serializers.ModelSerializer):
    registration_is_open = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()

    class Meta:
        model = CampEdition
        fields = (
            "id",
            "name",
            "year",
            "camp_start_date",
            "camp_end_date",
            "registration_open_date",
            "registration_close_date",
            "registration_status",
            "registration_is_open",
            "general_information",
            "categories",
        )

    def get_registration_is_open(self, edition):
        today = timezone.localdate()
        return (
            edition.registration_status == CampEdition.RegistrationStatus.OPEN
            and edition.registration_open_date <= today <= edition.registration_close_date
        )

    def get_categories(self, edition):
        return RegistrationCategoryOptionSerializer(
            edition.registration_categories.all(),
            many=True,
        ).data


class PrimaryRegistrantInputSerializer(StrictSerializer):
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class ParticipantInputSerializer(StrictSerializer):
    category_id = serializers.IntegerField(min_value=1)
    full_name = serializers.CharField(max_length=200)
    address = serializers.CharField()
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField()
    date_of_birth = serializers.DateField()
    sex = serializers.ChoiceField(choices=Participant.Sex.choices)
    height_cm = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    weight_kg = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    academic_status = serializers.ChoiceField(
        choices=Participant.AcademicStatus.choices
    )
    occupation = serializers.ChoiceField(choices=Participant.Occupation.choices)
    marital_status = serializers.ChoiceField(
        choices=Participant.MaritalStatus.choices
    )

    def validate_date_of_birth(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value


class RegistrationOrderCreateSerializer(StrictSerializer):
    primary_registrant = PrimaryRegistrantInputSerializer(
        required=False,
        default=dict,
    )
    participants = ParticipantInputSerializer(many=True, allow_empty=False)


class PrimaryRegistrantReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrimaryRegistrant
        fields = ("full_name", "phone", "email")


class RegistrationOrderItemReadSerializer(serializers.ModelSerializer):
    participant_id = serializers.UUIDField(read_only=True)
    category_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = RegistrationOrderItem
        fields = (
            "participant_id",
            "category_id",
            "category_name_snapshot",
            "fee_snapshot_ngn",
            "participant_snapshot",
        )


class RegistrationOrderReadSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="public_id", read_only=True)
    edition_name = serializers.CharField(source="edition.name", read_only=True)
    primary_registrant = PrimaryRegistrantReadSerializer(read_only=True)
    total_amount_ngn = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    items = RegistrationOrderItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = RegistrationOrder
        fields = (
            "order_id",
            "edition_name",
            "status",
            "payment_status",
            "total_amount_ngn",
            "created_at",
            "submitted_at",
            "primary_registrant",
            "items",
        )
