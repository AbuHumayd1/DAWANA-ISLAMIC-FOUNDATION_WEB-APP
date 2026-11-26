from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .participant_api import PortalView
from .camp_release_api import scoped_item
from .payment_return import ReturnBaseView, _authorize, _session_digest
from .tickets import ticket_manifest, ticket_pdf

def requested_item(request):
    value = request.query_params.get('ticket_item')
    if value is None:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 18:
        raise ValidationError('Invalid ticket selection.')
    return int(value)

class CamperTicketsView(PortalView):
    def get(self, request):
        item = scoped_item(request)
        if request.query_params.get('download') == '1':
            return ticket_pdf(item.order, requested_item(request))
        data = ticket_manifest(item.order, 'dic:camper-tickets')
        suffix = '?item_id=' + str(item.pk) + '&download=1'
        data['group_url'] += suffix
        for row in data['individuals']:
            row['url'] += '&item_id=' + str(item.pk) + '&download=1'
        return Response(data)

class PaymentReturnTicketsView(ReturnBaseView):
    def post(self, request, public_id):
        order = _authorize(_session_digest(request), public_id)
        return ticket_pdf(order, requested_item(request))
