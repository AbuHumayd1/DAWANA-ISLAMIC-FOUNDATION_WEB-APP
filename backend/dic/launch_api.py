from django.db import connection
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .participant_api import PortalView
from .feedback_services import portal_item
from .models import CampAnnouncement
from .launch_services import assigned_class


class CampUpdatesView(PortalView):
    def get(self,request):
        try: item_id=int(request.query_params.get('item_id',''))
        except (TypeError,ValueError): raise ValidationError('Choose a participant.') from None
        item=portal_item(request,item_id)
        edition=item.order.edition
        ready=CampAnnouncement._meta.db_table in connection.introspection.table_names()
        now=timezone.now()
        rows=CampAnnouncement.objects.filter(edition=edition,status='published').filter(
            Q(starts_at__isnull=True)|Q(starts_at__lte=now)).filter(Q(ends_at__isnull=True)|Q(ends_at__gt=now)) if ready else []
        return Response(dict(announcements_ready=ready,announcements=[dict(id=r.pk,title=r.title,body=r.body,date=r.updated_at.isoformat()) for r in rows],
            academic_class={'status':'not_applicable','name':None} if item.order.registration_basis=='tutor' else assigned_class(item.participant_id,edition)))
