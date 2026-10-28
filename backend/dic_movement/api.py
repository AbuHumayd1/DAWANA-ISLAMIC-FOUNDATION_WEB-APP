from uuid import UUID
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from dic.operations_api import OperationsBaseView, _edition_from_request
from dic.checkin_services import checkin_summary, require_checkin_storage
from dic.models import RegistrationOrderItem
from .services import require, storage, resolve_token, snapshot, record_movement, scan_arrival, serialize


def edition_from(request):
    if not request.query_params.get('edition'):
        raise ValidationError('Select an explicit camp edition.')
    return _edition_from_request(request)


class ScanView(OperationsBaseView):
    def post(self, request):
        require(request.user, 'dic.can_view_dic_ids')
        if not isinstance(request.data, dict):
            raise ValidationError('Send a scan action object.')
        edition = edition_from(request)
        action = request.data.get('action', 'preview')
        if action not in ('preview', 'arrive', 'departure', 'return'):
            raise ValidationError('Choose a supported scan action.')
        enrollment = resolve_token(request.data.get('token'), edition, request.user)
        if action == 'arrive':
            if request.data.get('confirmed') is not True:
                raise ValidationError('Confirm initial arrival explicitly.')
            require_checkin_storage()
            row, created = scan_arrival(edition, request.data.get('token'), request.user)
            return Response(dict(created=created, check_in=checkin_summary(row)), status=201 if created else 200)
        if action == 'preview':
            require_checkin_storage()
            from dic.models import CampCheckIn
            arrival = CampCheckIn.objects.filter(edition=edition, participant_id=enrollment.participant_id).select_related('checked_in_by').first()
            state = dict(check_in=checkin_summary(arrival))
            if request.user.has_perm('dic_movement.can_view_movements'):
                storage()
                state = snapshot(edition, enrollment.participant_id, request.user)
            return Response(dict(participant_id=str(enrollment.participant_id), name=enrollment.participant.full_name,
                participant_number=enrollment.participant_number, edition_id=edition.pk,
                **state))
        storage()
        try:
            row, created = record_movement(edition, enrollment.participant_id, request.user, request.data, token=request.data.get('token'))
        except IntegrityError:
            raise ValidationError('A concurrent request was recorded. Refresh before retrying.')
        return Response(dict(created=created, event=serialize(row)), status=201 if created else 200)


class MovementView(OperationsBaseView):
    def get(self, request):
        require(request.user, 'dic_movement.can_view_movements')
        edition = edition_from(request)
        participant_id = self.subject(edition, request.query_params.get('participant_id'))
        storage()
        return Response(snapshot(edition, participant_id, request.user))

    def subject(self, edition, value):
        try:
            participant_id = UUID(str(value))
        except ValueError:
            raise ValidationError('Select a valid camper.')
        if not RegistrationOrderItem.objects.filter(order__edition=edition, participant_id=participant_id).exists():
            raise ValidationError('Camper not found in the selected edition.')
        return participant_id

    def post(self, request):
        require(request.user, 'dic_movement.can_record_movements')
        require(request.user, 'dic_movement.can_view_movements')
        if not isinstance(request.data, dict):
            raise ValidationError('Send a movement object.')
        edition = edition_from(request)
        participant_id = self.subject(edition, request.data.get('participant_id'))
        storage()
        try:
            row, created = record_movement(edition, participant_id, request.user, request.data)
        except IntegrityError:
            raise ValidationError('A concurrent request was recorded. Refresh before retrying.')
        return Response(dict(created=created, event=serialize(row)), status=201 if created else 200)
