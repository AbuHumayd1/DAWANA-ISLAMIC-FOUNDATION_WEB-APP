"""Publication-gated carousel API. Existing source models remain authoritative."""
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .studio_api import StudioView, LIBRARIES
from .studio_catalogue_api import source_for, source_published, published_url
from .studio_carousel_models import (
    StudioCarousel, StudioCarouselSlide, StudioCarouselPlacement,
    CAROUSEL_DESTINATIONS, validate_carousel_audio,
)
from .studio_models import StudioAsset
from .models import CampEdition, DICAdminAuditEvent

IMAGE_KINDS = {'photos', 'flyers', 'activities', 'appearances'}
VIDEO_KINDS = {'hosted', 'videos', 'promotions'}
ALLOWED_DESTINATIONS = dict(CAROUSEL_DESTINATIONS)


def publisher(user):
    if not (user.is_active and user.is_staff and (
        user.is_superuser or user.has_perm('dic.publish_studio_placements'))):
        raise PermissionDenied('Media publishing permission required.')


def editor(user):
    if not (user.is_active and user.is_staff and (
        user.is_superuser or user.has_perm('dic.manage_studio_assets') or
        user.has_perm('dic.publish_studio_placements'))):
        raise PermissionDenied('Media editing permission required.')


def audit(user, action, carousel):
    DICAdminAuditEvent.objects.create(actor=user, action=action,
        target_type='StudioCarousel', target_id=str(carousel.pk),
        details={'format': carousel.format, 'preserved_source_files': True})


def serialize(carousel):
    return {
        'id': str(carousel.pk), 'title': carousel.title,
        'description': carousel.description, 'format': carousel.format,
        'state': carousel.state, 'loop_audio': carousel.loop_audio,
        'has_audio': bool(carousel.soundtrack),
        'deleted': carousel.deleted_at is not None,
        'slides': [{'asset_id': str(slide.asset_id), 'title': slide.asset.title,
                    'kind': slide.asset.source_kind, 'caption': slide.caption}
                   for slide in carousel.slides.all()],
        'destinations': [{'destination': row.destination, 'edition': row.edition_id}
                         for row in carousel.placements.all()],
    }


def choose_slides(user, fmt, supplied):
    if not isinstance(supplied, list) or not 2 <= len(supplied) <= 40:
        raise ValidationError({'slides': 'Choose between 2 and 40 slides.'})
    ids = []
    captions = []
    for row in supplied:
        if not isinstance(row, dict) or not isinstance(row.get('asset_id'), str):
            raise ValidationError({'slides': 'Each slide must reference an approved asset.'})
        caption = row.get('caption', '')
        if not isinstance(caption, str) or len(caption) > 300:
            raise ValidationError({'slides': 'Invalid slide caption.'})
        ids.append(row['asset_id'])
        captions.append(caption)
    if len(set(ids)) != len(ids):
        raise ValidationError({'slides': 'An asset may appear only once in a carousel.'})
    from uuid import UUID
    try:
        ids = [UUID(raw) for raw in ids]
    except (TypeError, ValueError, AttributeError):
        raise ValidationError({'slides': 'Invalid media asset identifier.'}) from None
    assets = StudioAsset.objects.filter(pk__in=ids, archived_at__isnull=True)
    mapping = {a.pk: a for a in assets}
    if len(mapping) != len(ids):
        raise ValidationError({'slides': 'A referenced media asset was not found or is archived.'})
    chosen = []
    for index, asset_id in enumerate(ids):
        asset = mapping[asset_id]
        if not (user.is_superuser or user.has_perm('dic.view_' + LIBRARIES[asset.source_kind][1])):
            raise PermissionDenied('No permission to access one of the selected media sources.')
        source = source_for(asset)
        if not source_published(asset, source) or not published_url(asset, source):
            raise ValidationError({'slides': 'Each slide must reference a currently approved and publicly deliverable media item.'})
        is_image = asset.source_kind in IMAGE_KINDS
        is_video = asset.source_kind in VIDEO_KINDS
        if not (is_image or is_video) or (fmt == 'images' and not is_image) or (fmt == 'videos' and not is_video):
            raise ValidationError({'slides': 'Media sources do not match the selected carousel format.'})
        chosen.append((asset, captions[index]))
    if fmt == 'mixed' and (not any(a.source_kind in IMAGE_KINDS for a, _ in chosen)
                          or not any(a.source_kind in VIDEO_KINDS for a, _ in chosen)):
        raise ValidationError({'format': 'Mixed carousels need at least one image and one video.'})
    return chosen


def choose_destinations(data):
    if not isinstance(data, list) or not 1 <= len(data) <= 4:
        raise ValidationError({'destinations': 'Choose one or more publication destinations.'})
    seen = set()
    placements = []
    for item in data:
        if not isinstance(item, dict) or item.get('destination') not in ALLOWED_DESTINATIONS:
            raise ValidationError({'destinations': 'Unsupported publication destination.'})
        destination = item['destination']
        if destination in seen:
            raise ValidationError({'destinations': 'Each destination can be chosen only once.'})
        seen.add(destination)
        edition_raw = item.get('edition')
        if destination.startswith('dic_'):
            try:
                edition_id = int(edition_raw)
            except (ValueError, TypeError):
                raise ValidationError({'edition': 'Choose an exact camp edition.'}) from None
            if not CampEdition.objects.filter(pk=edition_id, is_active=True).exists():
                raise ValidationError({'edition': 'The camp edition must exist and be active.'})
        else:
            if edition_raw not in (None, ''):
                raise ValidationError({'edition': 'Foundation-wide content is not edition scoped.'})
            edition_id = None
        placements.append((destination, edition_id))
    return placements


class StudioCarouselsView(StudioView):
    def get(self, request):
        editor(request.user)
        qs = StudioCarousel.objects.filter(deleted_at__isnull=True).prefetch_related('slides__asset', 'placements').order_by('-created_at')[:100]
        return self.nocache({'carousels': [serialize(row) for row in qs]})

    def post(self, request):
        editor(request.user)
        title = request.data.get('title')
        fmt = request.data.get('format')
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise ValidationError({'title': 'Enter a title of up to 300 characters.'})
        if fmt not in ('images', 'videos', 'mixed'):
            raise ValidationError({'format': 'Choose image, video or mixed carousel.'})
        with transaction.atomic():
            carousel = StudioCarousel.objects.create(title=title.strip(), format=fmt, created_by=request.user)
            audit(request.user, 'studio_carousel_created', carousel)
        return self.nocache({'carousel': serialize(carousel)}, status=201)


class StudioCarouselDetailView(StudioView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def patch(self, request, carousel_id):
        editor(request.user)
        with transaction.atomic():
            carousel = get_object_or_404(StudioCarousel.objects.select_for_update(), pk=carousel_id, deleted_at__isnull=True)
            if carousel.state == 'published':
                raise ValidationError({'detail': 'Withdraw the carousel before changing slides or audio.'})
            if 'title' in request.data:
                title = request.data['title']
                if not isinstance(title, str) or not title.strip() or len(title) > 300:
                    raise ValidationError({'title': 'Invalid title.'})
                carousel.title = title.strip()
            if 'description' in request.data:
                description = request.data['description']
                if not isinstance(description, str) or len(description) > 5000:
                    raise ValidationError({'description': 'Invalid description.'})
                carousel.description = description
            if 'loop_audio' in request.data:
                carousel.loop_audio = request.data['loop_audio'] in (True, 'true', '1')
            if 'soundtrack' in request.FILES:
                audio = request.FILES['soundtrack']
                validate_carousel_audio(audio)
                carousel.soundtrack = audio
            if request.data.get('remove_audio') in (True, 'true', '1'):
                carousel.soundtrack = ''
            if 'slides' in request.data:
                slides = choose_slides(request.user, carousel.format, request.data['slides'])
                carousel.slides.all().delete()
                StudioCarouselSlide.objects.bulk_create([
                    StudioCarouselSlide(carousel=carousel, asset=asset, order=index, caption=caption)
                    for index, (asset, caption) in enumerate(slides)])
            carousel.full_clean()
            carousel.save()
            audit(request.user, 'studio_carousel_edited', carousel)
        return self.nocache({'carousel': serialize(carousel)})

    def post(self, request, carousel_id):
        publisher(request.user)
        action = request.data.get('action')
        if action not in ('publish', 'withdraw', 'delete'):
            raise ValidationError({'action': 'Choose publish, withdraw or delete.'})
        with transaction.atomic():
            carousel = get_object_or_404(StudioCarousel.objects.select_for_update(), pk=carousel_id, deleted_at__isnull=True)
            if action == 'publish':
                slides = [{'asset_id': str(s.asset_id), 'caption': s.caption} for s in carousel.slides.order_by('order')]
                choose_slides(request.user, carousel.format, slides)
                placements = choose_destinations(request.data.get('destinations'))
                carousel.placements.all().delete()
                StudioCarouselPlacement.objects.bulk_create([
                    StudioCarouselPlacement(carousel=carousel, destination=destination,
                                            edition_id=edition_id, published_at=timezone.now())
                    for destination, edition_id in placements])
                carousel.state = 'published'
                carousel.published_at = timezone.now()
            else:
                carousel.state = 'withdrawn'
                carousel.placements.all().delete()
                if action == 'delete':
                    carousel.deleted_at = timezone.now()
            carousel.save()
            audit(request.user, 'studio_carousel_' + action, carousel)
        return self.nocache({'carousel': serialize(carousel)})


class PublicStudioCarouselsView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        destination = request.query_params.get('destination', '')
        if destination not in ALLOWED_DESTINATIONS:
            raise ValidationError({'destination': 'Unsupported destination.'})
        qs = StudioCarousel.objects.filter(state='published', deleted_at__isnull=True,
                    placements__destination=destination).distinct().prefetch_related('slides__asset', 'placements').order_by('-published_at')[:30]
        data = []
        for carousel in qs:
            matching = [p for p in carousel.placements.all() if p.destination == destination]
            if not matching or any(p.edition_id and not p.edition.is_active for p in matching):
                continue
            slides = []
            for slide in carousel.slides.all():
                source = source_for(slide.asset)
                url = published_url(slide.asset, source)
                if not source_published(slide.asset, source) or not url:
                    continue
                record = {'url': url, 'title': slide.asset.title,
                          'caption': slide.caption, 'kind': slide.asset.source_kind}
                if slide.asset.source_kind in ('hosted', 'videos'):
                    record['embed_url'] = url if slide.asset.source_kind == 'hosted' else None
                    if slide.asset.source_kind == 'videos':
                        from .video_providers import video_source
                        try:
                            record['embed_url'] = video_source(source.video_url)['embed_url']
                        except Exception:
                            continue
                slides.append(record)
            if len(slides) < 2:
                continue
            data.append({'id': str(carousel.pk), 'title': carousel.title,
                         'description': carousel.description, 'format': carousel.format,
                         'slides': slides, 'loop_audio': carousel.loop_audio,
                         'audio_url': '/api/v1/dic/studio/public-carousels/' + str(carousel.pk) + '/audio/'
                                      if carousel.soundtrack else None})
        response = Response({'items': data})
        response['Cache-Control'] = 'public, max-age=0, must-revalidate'
        return response


class PublicStudioCarouselAudioView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request, carousel_id):
        carousel = get_object_or_404(StudioCarousel, pk=carousel_id, state='published', deleted_at__isnull=True)
        if not carousel.soundtrack or not carousel.placements.exists():
            raise Http404
        if not any(p.edition_id is None or p.edition.is_active for p in carousel.placements.select_related('edition')):
            raise Http404
        name = carousel.soundtrack.name.lower()
        content_type = 'audio/mpeg' if name.endswith('.mp3') else 'audio/ogg' if name.endswith('.ogg') else 'audio/wav'
        response = FileResponse(carousel.soundtrack.open('rb'), content_type=content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
