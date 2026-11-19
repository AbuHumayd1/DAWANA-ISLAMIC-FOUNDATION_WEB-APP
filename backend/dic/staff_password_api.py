"""Self-service staff password changes; never a credential reset or privilege grant."""
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import DICAdminAuditEvent


class StaffChangePasswordView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'dic_ops_login'

    def post(self, request):
        user = request.user
        # Staff-only: never expose a bypass into participant account security.
        if not user.is_active or not user.is_staff or not (
            user.is_superuser or user.has_perm('dic.can_view_dic_operations')
            or self._studio_allowed(user)
        ):
            return Response({'detail': 'Staff account access required.'}, status=403)

        values = request.data
        current = values.get('current_password')
        new = values.get('new_password')
        confirm = values.get('confirm_password')
        if not all(isinstance(value, str) and 0 < len(value) <= 256
                   for value in (current, new, confirm)):
            return Response({'detail': 'Complete all three password fields.'}, status=400)
        if not user.check_password(current):
            return Response({'detail': 'Current password is incorrect.'}, status=400)
        if new != confirm:
            return Response({'detail': 'New passwords do not match.'}, status=400)
        if new == current:
            return Response({'detail': 'Choose a password different from your current one.'}, status=400)
        try:
            validate_password(new, user)
        except DjangoValidationError as error:
            return Response({'detail': ' '.join(error.messages)}, status=400)

        with transaction.atomic():
            # Lock the user row and verify the credential again under the lock.
            locked = type(user).objects.select_for_update().get(pk=user.pk)
            if not locked.is_active or not locked.is_staff or not locked.check_password(current):
                return Response({'detail': 'Current password is no longer valid.'}, status=400)
            locked.set_password(new)
            locked.save(update_fields=['password'])
            DICAdminAuditEvent.objects.create(
                actor=locked, action='staff_password_changed',
                target_type='User', target_id=str(locked.pk),
                details={'method': 'self_service'},
            )
        update_session_auth_hash(request, locked)
        response = Response({'detail': 'Password updated successfully.'})
        response['Cache-Control'] = 'no-store'
        return response

    @staticmethod
    def _studio_allowed(user):
        from .studio_api import studio_allowed
        return studio_allowed(user)
