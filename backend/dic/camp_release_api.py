"""Camper resources scoped by the existing authorized booking item."""
from pathlib import Path
from django.http import FileResponse,HttpResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as ModelError
from django.urls import reverse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .participant_api import PortalView
from .feedback_services import portal_item
from .models import LectureRecording,CampVideo,CertificateRelease,ParticipationCertificate
from .media_delivery import safe_media,media_headers
from .camp_content import audience_rows


def studio_audio_visible(row, edition):
    """Linked Studio recordings require an active camper destination.

    Unlinked legacy recordings retain their pre-existing release policy.
    Entitlement to a camper is still required by PortalView and scoped_item.
    """
    from .studio_models import StudioAsset, StudioPlacement
    source = StudioAsset.objects.filter(source_kind='recordings', source_id=row.pk).first()
    if source is None:
        return True
    if source.archived_at is not None:
        return False
    return StudioPlacement.objects.filter(
        asset=source, destination='camper_resources', edition=edition,
        state='published', published_at__isnull=False,
    ).exists()


def scoped_item(request):
    try:return portal_item(request,int(request.query_params.get('item_id','')))
    except (ValueError,TypeError):raise ValidationError('Choose an authorized camper.') from None


class CamperResourcesView(PortalView):
    def get(self,request):
        item=scoped_item(request)
        def data(row,kind):
            if kind == 'audio' and not studio_audio_visible(row, item.order.edition):
                return None
            if row.session_id and not audience_rows(
                    type(row.session).objects.filter(pk=row.session_id, status='published'),
                    item.participant, item.order.edition).exists():
                return None
            return dict(
                id=row.pk, kind=kind, title=row.title if kind=='audio' else row.caption,
                description=row.description, lecturer=row.lecturer,
                session=(row.session.title or row.session.description) if row.session else '',
                url=reverse('dic:camper-recording', args=[kind,row.pk])+'?item_id='+str(item.pk),
            )
        records=[]
        for model,kind in [(LectureRecording,'audio'),(CampVideo,'video')]:
            query=model.objects.filter(edition=item.order.edition,state='published',published_at__isnull=False).select_related('session')
            if kind=='video':query=query.exclude(recording_file='')
            for row in query[:100]:
                value=data(row,kind)
                if value:records.append(value)
        config=CertificateRelease.objects.filter(edition=item.order.edition).first()
        available=False
        if config and config.enabled and config.release_at and timezone.now()>=config.release_at:
            from .certificates import approved_artwork
            try:approved_artwork(config);available=True
            except ModelError:pass
        certificate=ParticipationCertificate.objects.filter(edition=item.order.edition,participant=item.participant).first()
        if certificate and certificate.revoked_at:available=False
        return Response(dict(recordings=records,certificate=dict(available=available,
            state='released' if available else 'not_released',url=reverse('dic:camper-certificate')+'?item_id='+str(item.pk) if available else None)))


class CamperRecordingView(PortalView):
    @safe_media
    def get(self,request,kind,pk):
        item=scoped_item(request)
        model=LectureRecording if kind=='audio' else CampVideo
        row=get_object_or_404(model,pk=pk,edition=item.order.edition,state='published',published_at__isnull=False)
        if kind == 'audio' and not studio_audio_visible(row, item.order.edition):
            from django.http import Http404
            raise Http404
        if row.session_id and not audience_rows(type(row.session).objects.filter(pk=row.session_id,status='published'),item.participant,item.order.edition).exists():
            from django.http import Http404
            raise Http404
        field=row.audio if kind=='audio' else row.recording_file
        if not field:
            from django.http import Http404
            raise Http404
        suffix=Path(field.name).suffix.lower()
        mime={'.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav','.ogg':'audio/ogg','.mp4':'video/mp4','.webm':'video/webm'}.get(suffix,'application/octet-stream')
        response=FileResponse(field.open('rb'),content_type=mime,as_attachment=request.query_params.get('download')=='1',filename='dic-recording'+suffix)
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        response=media_headers(response,public=False)
        response['Cross-Origin-Resource-Policy']='cross-origin'
        return response


class CamperCertificateView(PortalView):
    def get(self,request):
        item=scoped_item(request)
        from .certificates import issue,release_for,render_certificate
        try:
            config=release_for(item.order.edition);record=issue(item);payload=render_certificate(record,config)
        except ModelError as error:raise ValidationError('Certificate artwork or placement is awaiting administrator review.') from error
        response=HttpResponse(payload,content_type='application/pdf')
        response['Content-Disposition']='attachment; filename="DIC26-certificate-'+str(record.reference)+'.pdf"'
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        return response
