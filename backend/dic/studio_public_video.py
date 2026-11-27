from django.http import Http404, FileResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from .studio_models import StudioAsset
from .memory_models import CampVideo
from .media_delivery import safe_media, media_headers
from .promo_views import stream_video_field


def public_source(asset_id):
    asset = get_object_or_404(StudioAsset, pk=asset_id, source_kind='videos', archived_at__isnull=True)
    if not asset.placements.filter(state='published', published_at__isnull=False,
            destination__in=('foundation_archive','foundation_home','dic_landing')).filter(
            Q(edition__isnull=True) | Q(edition__is_active=True)).exists():
        raise Http404
    return get_object_or_404(CampVideo.objects.exclude(recording_file=''), pk=asset.source_id,
        state='published', published_at__isnull=False, session__isnull=True)


@require_safe
@safe_media
def public_video_stream(request, asset_id):
    return media_headers(stream_video_field(request, public_source(asset_id).recording_file), public=True)


@require_safe
@safe_media
def public_video_poster(request, asset_id):
    source = public_source(asset_id)
    return media_headers(FileResponse(source.thumbnail.open('rb'), content_type='image/jpeg'), public=True)
