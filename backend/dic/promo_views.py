"""Published-only editorial assets; range streaming never exposes R2 URLs."""
import re
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_safe
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .promo_models import PromoVideo, CampFlyer
from .media_delivery import safe_media, media_headers, media_chunks
from .promo_storage import MAX_VIDEO_BYTES
from django.core.exceptions import ValidationError


def asset(request, model, pk):
    query = model.objects.all()
    if request.GET.get('preview') == '1':
        if not (request.user.is_active and request.user.is_staff and request.user.has_perm(f'dic.view_{model._meta.model_name}')):
            raise Http404
    else:
        query = query.filter(state='published', published_at__isnull=False, edition__is_active=True)
    return get_object_or_404(query, pk=pk)


class DICEditorialView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        videos = PromoVideo.objects.filter(state='published', published_at__isnull=False, edition__is_active=True)
        def serialize(item):
            return {'id': item.pk, 'title': item.title, 'description': item.description,
                    'alt_text': item.alt_text, 'video_url': reverse('dic:promo-stream', args=[item.pk]),
                    'poster_url': reverse('dic:promo-poster', args=[item.pk])}
        flyer = CampFlyer.objects.filter(state='published', published_at__isnull=False, edition__is_active=True).first()
        response = Response({'experiences': [serialize(item) for item in videos.filter(kind='experience')[:3]],
                             'introductions': [serialize(item) for item in videos.filter(kind='introduction')[:2]],
                             'flyer': {'title': flyer.title, 'alt_text': flyer.alt_text, 'image_url': reverse('dic:official-flyer', args=[flyer.pk])} if flyer else None})
        response['Cache-Control'] = 'private, no-store'
        return response


def editorial_headers(response, request):
    # Only the published branch of asset() may grant public embedding.
    return media_headers(response, public=request.GET.get('preview') != '1')


@require_safe
@safe_media
def editorial_image(request, pk, kind):
    obj = asset(request, CampFlyer if kind == 'flyer' else PromoVideo, pk)
    field = obj.image if kind == 'flyer' else obj.poster
    response = FileResponse(field.open('rb'), content_type='image/jpeg')
    response['Content-Disposition'] = 'inline; filename="dic-image.jpg"'
    return editorial_headers(response, request)


def parse_range(value, size):
    if size <= 0:
        raise ValueError
    if not value:
        return 0, size - 1, False
    if len(value) > 70:
        raise ValueError
    match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', value)
    if not match or not any(match.groups()):
        raise ValueError
    left, right = match.groups()
    if left:
        start, end = int(left), min(int(right), size - 1) if right else size - 1
    else:
        suffix = int(right)
        if suffix <= 0:
            raise ValueError
        start, end = max(0, size - suffix), size - 1
    if start > end or start >= size:
        raise ValueError
    return start, end, True


@require_safe
@safe_media
def promo_stream(request, pk):
    obj = asset(request, PromoVideo, pk)
    storage, key = obj.video.storage, obj.video.name
    backend = storage._backend()
    client = None if backend else storage._client()
    size = backend.size(key) if backend else client.head_object(Bucket=storage._bucket(), Key=key)['ContentLength']
    if not 0 < size <= MAX_VIDEO_BYTES:
        raise ValidationError('Invalid stored video size.')
    try:
        start, end, partial = parse_range(request.headers.get('Range') if request.method == 'GET' else None, size)
    except ValueError:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{size}'
        return editorial_headers(response, request)
    length = end - start + 1
    if request.method == 'HEAD':
        response = HttpResponse(content_type='video/mp4', status=206 if partial else 200)
    else:
        if backend:
            body = backend.open(key, 'rb')
            body.seek(start)
        else:
            body = client.get_object(Bucket=storage._bucket(), Key=key, Range=f'bytes={start}-{end}')['Body']
        response = StreamingHttpResponse(media_chunks(body, length), content_type='video/mp4', status=206 if partial else 200)
        response._resource_closers.append(body.close)
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    response['Content-Disposition'] = 'inline; filename="dic-promotion.mp4"'
    if partial:
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    return editorial_headers(response, request)
