"""Staff field preparation and separately authorized assisted booking creation."""
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .campsite_api import require_campsite_staff
from .operations_api import OperationsBaseView
from .recovery import normalize_phone
from .serializers import StrictSerializer, RegistrationOrderCreateSerializer, PrimaryRegistrantInputSerializer
from rest_framework import serializers
from django.conf import settings


class AssistedPrimaryContact(PrimaryRegistrantInputSerializer):
    # Preserve the existing staff-assisted phone recovery path. This does not
    # authorize portal access or email account creation.
    email = serializers.EmailField(required=False, allow_blank=True)


class AssistedOrderInput(RegistrationOrderCreateSerializer):
    portal_account = None  # Staff must never choose or collect a camper password.
    primary_registrant = AssistedPrimaryContact()


class AssistedPreparationInput(StrictSerializer):
    registration = AssistedOrderInput()


def validate_preparation(data):
    serializer = AssistedPreparationInput(data=data)
    serializer.is_valid(raise_exception=True)
    registration = serializer.validated_data['registration']
    payer = registration.get('primary_registrant', {})
    if not payer.get('full_name', '').strip():
        raise ValidationError({'primary_registrant': 'Provide the payer or responsible registrant name.'})
    if not payer.get('email') and not payer.get('phone'):
        raise ValidationError({'primary_registrant': 'Provide the payer’s own recoverable email or phone, not the officer’s contact.'})
    if payer.get('phone'):
        try:
            normalize_phone(payer['phone'])
        except (ValueError, AttributeError):
            raise ValidationError({'primary_registrant': 'Provide a valid recovery phone number.'})
    # No pricing reservation, eligibility decision, identity match or persistence.
    return {'fields_valid': True, 'registration_created': False, 'payment_started': False,
        'message': 'Required details pass field checks. No booking was created and no price or place was reserved. Complete registration on the payer’s device.'}


class AssistedRegistrationPreparationView(OperationsBaseView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_campsite_staff(request.user)

    def get(self, request):
        enabled = bool(getattr(settings, 'DIC_ASSISTED_BOOKING_ENABLED', False)
            and request.user.has_perm('dic_assistance.can_assist_registration'))
        return Response({'mode': 'assisted_creation' if enabled else 'preparation_only', 'creation_enabled': enabled,
            'can_create_assisted': enabled,
            'registration_path': '/dic/register', 'recovery_path': '/dic/register/recover'})

    def post(self, request):
        # Strict request shape rejects create/pay/status/actor/token override fields.
        return Response(validate_preparation(request.data))


class AssistedCreationInput(AssistedPreparationInput):
    request_id = serializers.UUIDField()


class AssistedBookingCreateView(OperationsBaseView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from dic_assistance.services import require_assistance
        require_assistance(request.user)
        if not getattr(settings, 'DIC_ASSISTED_BOOKING_ENABLED', False):
            from rest_framework.exceptions import APIException
            error = APIException('Assisted creation is disabled pending migration and acceptance approval.')
            error.status_code = 503
            raise error

    def post(self, request):
        from dic_assistance.services import create_assistance
        serializer = AssistedCreationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Preserve stricter preparation contact checks, without passing request_id.
        validate_preparation({'registration': request.data.get('registration')})
        result = create_assistance(request.user, serializer.validated_data['request_id'],
                                   serializer.validated_data['registration'])
        return Response(result, status=200 if result['idempotent_replay'] else 201)
