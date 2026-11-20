"""Safe unified catalogue and destination publication actions.

Only source-validated, already published media can ever be exposed publicly.
A placement does not override the original model's publication/edition guard.
"""
from pathlib import Path
from django.db import transaction
from django.http import FileResponse, Http404
from .media_delivery import safe_media, media_headers
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .studio_models import StudioAsset, StudioPlacement, SUPPORTED_DESTINATIONS, DESTINATIONS
from .studio_api import StudioView, LIBRARIES
from .models import DICAdminAuditEvent, CampEdition


def require_catalogue(user):
    if not (user.is_superuser or user.has_perm('dic.manage_studio_assets')):
        raise PermissionDenied('Studio catalogue management permission required.')


def require_placement_publisher(user):
    if not (user.is_superuser or user.has_perm('dic.publish_studio_placements')):
        raise PermissionDenied('Studio destination publishing permission required.')


def require_source_view(user, asset):
    if asset.source_kind not in LIBRARIES:
        raise NotFound('Unknown media source.')
    code = LIBRARIES[asset.source_kind][1]
    if not (user.is_superuser or user.has_perm('dic.view_' + code)):
        raise PermissionDenied('This media source is not accessible to your staff role.')


def source_for(asset):
    if asset.source_kind not in LIBRARIES:
        raise ValidationError('Unsupported source type.')
    model = LIBRARIES[asset.source_kind][0]
    return model.objects.filter(pk=asset.source_id).first()


def source_published(asset, source):
    if source is None or asset.archived_at is not None:
        return False
    if asset.source_kind == 'lecturers':
        # Lecturer identity source is not itself published; appearances are gated.
        return False
    return getattr(source, 'state', None) == 'published' and bool(getattr(source, 'published_at', None))


def published_url(asset, source):
    if not source_published(asset, source):
        return None
    if asset.source_kind == 'photos':
        return reverse('dic:memory-image', args=[source.pk])
    if asset.source_kind == 'hosted':
        # Treat disallowed/withdrawn providers as absent, never a public 500.
        from .video_providers import video_source
        from django.core.exceptions import ValidationError as ModelValidationError
        try:
            return video_source(source.video_url)['embed_url']
        except ModelValidationError:
            return None
    if asset.source_kind == 'videos':
        # Publicly approved hosted videos have a server-served thumbnail.
        # Uploaded recordings stay on the camper-entitlement endpoint.
        if source.video_url and not source.recording_file and source.thumbnail:
            from .video_providers import video_source
            from django.core.exceptions import ValidationError as ModelValidationError
            try:
                video_source(source.video_url)
                return reverse('dic:video-thumbnail', args=[source.pk])
            except ModelValidationError:
                return None
        return None
    if asset.source_kind == 'flyers':
        return reverse('dic:official-flyer', args=[source.pk]) if source.edition.is_active else None
    if asset.source_kind == 'promotions':
        return reverse('dic:promo-stream', args=[source.pk]) if source.edition.is_active else None
    if asset.source_kind == 'appearances':
        if source.edition.is_active and source.lecturer.photograph and source.confirmation_status != 'declined':
            return reverse('dic:showcase-image', args=['lecturer', source.pk])
        return None
    if asset.source_kind == 'activities':
        return reverse('dic:showcase-image', args=['activity', source.pk]) if source.photograph and source.edition.is_active else None
    return None  # Recordings are ONLY accessible via existing camper entitlement routes.


def summary(asset):
    return {'id': str(asset.pk), 'source_kind': asset.source_kind, 'source_id': asset.source_id,
            'title': asset.title, 'description': asset.description, 'album': asset.album,
            'campaign': asset.campaign, 'programme': asset.programme, 'event': asset.event,
            'archived': asset.archived_at is not None,
            'destinations': [
                {'id': p.pk, 'destination': p.destination, 'edition': p.edition_id, 'state': p.state}
                for p in asset.placements.all()]}


class StudioAssetsView(StudioView):
    def get(self, request):
        require_catalogue(request.user)
        raw_page = request.query_params.get('page', '1')
        if not raw_page.isascii() or not raw_page.isdigit() or not 1 <= len(raw_page) <= 3:
            raise ValidationError({'page': 'Choose a valid catalogue page.'})
        page = int(raw_page)
        if not 1 <= page <= 100:
            raise ValidationError({'page': 'Catalogue page out of range.'})
        from django.db.models import Q
        allowed = [kind for kind, (_, codename, _) in LIBRARIES.items()
                   if request.user.is_superuser or request.user.has_perm('dic.view_' + codename)]
        kind = request.query_params.get('kind', '')
        term = request.query_params.get('q', '').strip()
        album = request.query_params.get('album', '').strip()
        if kind and kind not in allowed:
            raise PermissionDenied('This media collection is not accessible to your staff role.')
        if len(term) > 100 or len(album) > 150:
            raise ValidationError({'filters': 'Search or album filter is too long.'})
        if album and kind != 'photos':
            raise ValidationError({'album': 'Select the photography collection before filtering albums.'})
        queryset = StudioAsset.objects.filter(source_kind__in=allowed)
        if kind:
            queryset = queryset.filter(source_kind=kind)
        if album:
            queryset = queryset.filter(album=album)
        if term:
            queryset = queryset.filter(
                Q(title__icontains=term) | Q(album__icontains=term) |
                Q(campaign__icontains=term) | Q(programme__icontains=term) |
                Q(event__icontains=term))
        # Album navigation is server-filtered, never limited to the loaded page.
        # Only names visible to the requesting media role can be returned.
        albums = []
        if kind == 'photos':
            albums = list(StudioAsset.objects.filter(source_kind='photos', source_kind__in=allowed)
                          .exclude(album='').order_by('album')
                          .values_list('album', flat=True).distinct()[:100])
        offset = (page - 1) * 30
        records = list(queryset.prefetch_related('placements')
                       .order_by('-created_at', '-pk')[offset:offset + 31])
        results = [summary(item) for item in records[:30]]
        return self.nocache({'assets': results, 'page': page, 'has_more': len(records) > 30,
                             'albums': albums,
                             'destinations': [{'key': k, 'name': v} for k, v in DESTINATIONS],
                             'can_publish': bool(request.user.is_superuser or request.user.has_perm('dic.publish_studio_placements'))})

    def post(self, request):
        require_catalogue(request.user)
        data = request.data
        kind = data.get('source_kind', '')
        if kind not in LIBRARIES:
            raise ValidationError({'source_kind': 'Choose an existing media library.'})
        _, code, label = LIBRARIES[kind]
        if not request.user.is_superuser and not request.user.has_perm('dic.view_' + code):
            raise PermissionDenied('Media library access required.')
        try:
            source_id = int(data.get('source_id'))
        except (TypeError, ValueError):
            raise ValidationError({'source_id': 'Choose an existing media record.'}) from None
        if source_id <= 0:
            raise ValidationError({'source_id': 'Choose an existing media record.'})
        source = LIBRARIES[kind][0].objects.filter(pk=source_id).first()
        if not source:
            raise NotFound('Media source not found.')
        with transaction.atomic():
            asset, created = StudioAsset.objects.get_or_create(
                source_kind=kind, source_id=source_id,
                defaults={'title': str(getattr(source, label, '') or source)[:300],
                          'created_by': request.user})
            DICAdminAuditEvent.objects.create(actor=request.user,
                action='studio_source_linked' if created else 'studio_source_link_reused',
                target_type='StudioAsset', target_id=str(asset.pk),
                details={'source_kind': kind, 'source_id': source_id})
        return self.nocache({'asset': summary(asset), 'created': created}, status=201 if created else 200)


class StudioAssetDetailView(StudioView):
    def patch(self, request, asset_id):
        require_catalogue(request.user)
        allowed = {'title', 'description', 'album', 'campaign', 'programme', 'event'}
        if not isinstance(request.data, dict) or not request.data or not set(request.data) <= allowed:
            raise ValidationError({'detail': 'Only descriptive catalogue metadata can be edited.'})
        with transaction.atomic():
            asset = get_object_or_404(StudioAsset.objects.select_for_update(), pk=asset_id)
            require_source_view(request.user, asset)
            for key, value in request.data.items():
                field = StudioAsset._meta.get_field(key)
                maximum = field.max_length or 5000
                if not isinstance(value, str) or len(value) > maximum:
                    raise ValidationError({key: 'Invalid or oversized text.'})
                setattr(asset, key, value)
            asset.full_clean()
            asset.save()
            DICAdminAuditEvent.objects.create(actor=request.user, action='studio_asset_metadata_updated',
                target_type='StudioAsset', target_id=str(asset.pk),
                details={'fields': sorted(request.data)})
        return self.nocache({'asset': summary(asset)})

    def post(self, request, asset_id):
        require_catalogue(request.user)
        if request.data.get('action') not in ('archive', 'restore'):
            raise ValidationError({'action': 'Choose archive or restore.'})
        with transaction.atomic():
            asset = get_object_or_404(StudioAsset.objects.select_for_update(), pk=asset_id)
            require_source_view(request.user, asset)
            if request.data['action'] == 'archive':
                asset.archived_at = timezone.now()
                StudioPlacement.objects.filter(asset=asset).update(
                    state='withdrawn', published_at=None, published_by=None)
            else:
                asset.archived_at = None
            asset.save(update_fields=['archived_at', 'updated_at'])
            DICAdminAuditEvent.objects.create(actor=request.user, action='studio_asset_' + request.data['action'],
                target_type='StudioAsset', target_id=str(asset.pk), details={})
        return self.nocache({'asset': summary(asset)})


class StudioPlacementView(StudioView):
    def post(self, request, asset_id):
        require_placement_publisher(request.user)
        destination = request.data.get('destination', '')
        action = request.data.get('action', 'draft')
        if action not in ('draft', 'publish', 'withdraw'):
            raise ValidationError({'action': 'Choose draft, publish or withdraw.'})
        edition_id = request.data.get('edition') or None
        if edition_id is not None and (not str(edition_id).isascii() or
                                       not str(edition_id).isdigit() or len(str(edition_id)) > 9):
            raise ValidationError({'edition': 'Select a valid edition.'})
        edition_id = int(edition_id) if edition_id is not None else None
        with transaction.atomic():
            asset = get_object_or_404(StudioAsset.objects.select_for_update(), pk=asset_id)
            require_source_view(request.user, asset)
            if destination not in SUPPORTED_DESTINATIONS[asset.source_kind]:
                raise ValidationError({'destination': 'Destination not permitted for this media type.'})
            source = source_for(asset)
            if source is None:
                raise NotFound('Media source was withdrawn.')
            if action == 'publish' and destination == 'dic_landing' and asset.source_kind == 'flyers':
                raise ValidationError({'destination': 'Official DIC flyers appear in their dedicated invitation section; use the Foundation media archive for additional distribution.'})
            if action == 'publish' and not source_published(asset, source):
                raise ValidationError({'action': 'Publish the validated source first. Archived or draft media cannot be distributed.'})
            if action == 'publish' and destination == 'foundation_archive' and asset.source_kind == 'recordings':
                # Keep camp session audience boundaries enforced.
                if source.session_id:
                    raise ValidationError({'action': 'Recordings attached to a camp session cannot be made public. Use Camper Portal resources instead.'})
                if not source.audio:
                    raise ValidationError({'action': 'A validated audio file is required before public publication.'})
            elif action == 'publish' and destination not in ('camper_resources', 'dic_resources') and not published_url(asset, source):
                raise ValidationError({'action': 'No publicly deliverable media is available for this destination.'})
            if edition_id and not CampEdition.objects.filter(pk=edition_id).exists():
                raise ValidationError({'edition': 'Choose an existing camp edition.'})
            # Preserve original DIC ownership for all participant or camp-specific placements.
            if (edition_id is not None and hasattr(source, 'edition_id')
                    and (asset.source_kind != 'hosted' or source.edition_id is not None)
                    and source.edition_id != edition_id):
                raise ValidationError({'edition': 'An asset cannot cross its original DIC edition private delivery boundary.'})
            placement, _ = StudioPlacement.objects.select_for_update().get_or_create(
                asset=asset, destination=destination, edition_id=edition_id)
            placement.state = {'draft': 'draft', 'publish': 'published', 'withdraw': 'withdrawn'}[action]
            placement.full_clean()
            placement.published_by = request.user if action == 'publish' else None
            placement.published_at = timezone.now() if action == 'publish' else None
            placement.save()
            DICAdminAuditEvent.objects.create(actor=request.user, action='studio_placement_' + action,
                target_type='StudioPlacement', target_id=str(placement.pk),
                details={'asset_id': str(asset.pk), 'destination': destination, 'edition': edition_id})
        if action == 'publish' and destination == 'foundation_archive':
            from .studio_notifications import notify_public_placement
            notification = notify_public_placement(placement.pk)
        else:
            notification = 'not_sent'
        return self.nocache({'asset': summary(asset), 'placement_id': placement.pk,
                             'notification': notification})


class PublicStudioPlacementsView(APIView):
    """Public metadata is filtered by BOTH placement and live legacy content."""
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        destination = request.query_params.get('destination', 'foundation_archive')
        public = {'foundation_archive', 'foundation_home', 'dic_memories', 'dic_landing', 'dic_resources'}
        if destination not in public:
            raise NotFound()
        page_text = request.query_params.get('page', '1')
        if not page_text.isascii() or not page_text.isdigit() or not 1 <= len(page_text) <= 3:
            raise ValidationError({'page': 'Choose a valid archive page.'})
        page = int(page_text)
        if not 1 <= page <= 100:
            raise ValidationError({'page': 'Archive page out of range.'})
        if destination == 'foundation_home' and page != 1:
            return Response({'items': [], 'page': page, 'has_more': False})
        offset = (page - 1) * 200
        placements_query = StudioPlacement.objects.filter(
            destination=destination, state='published', asset__archived_at__isnull=True,
        )
        # The dedicated DIC flyer block is the canonical home for official flyers.
        # Exclude them before pagination so no empty highlights section is rendered.
        if destination == 'dic_landing':
            placements_query = placements_query.exclude(asset__source_kind='flyers')
        placements = list(placements_query.select_related('asset', 'edition')
                          .order_by('-published_at', '-pk')[offset:offset + 201])
        rows = []
        for placement in placements[:200]:
            if placement.edition_id and not placement.edition.is_active:
                continue
            # DIC resources is public for hosted video only; lecture audio is private.
            if destination == 'dic_resources' and placement.asset.source_kind != 'hosted':
                continue
            source = source_for(placement.asset)
            url = published_url(placement.asset, source)
            if placement.asset.source_kind == 'recordings' and destination == 'foundation_archive':
                url = reverse('dic:studio-public-audio', args=[placement.asset.pk]) if (
                    source_published(placement.asset, source) and not source.session_id and source.audio) else None
            if url:
                item = {'title': placement.asset.title, 'description': placement.asset.description,
                        'programme': placement.asset.programme, 'event': placement.asset.event,
                        'edition': placement.edition.year if placement.edition_id else (
                            source.edition.year if getattr(source, 'edition_id', None) and
                            placement.asset.source_kind in ('recordings', 'videos', 'hosted', 'promotions')
                            else None),
                        'source_kind': placement.asset.source_kind, 'url': url,
                        'album': placement.asset.album,
                        'lecturer': str(getattr(source, 'lecturer', '') or '')[:200]}
                if placement.asset.source_kind == 'hosted':
                    item['embed_url'] = url
                if placement.asset.source_kind == 'videos':
                    from .video_providers import video_source
                    item['embed_url'] = video_source(source.video_url)['embed_url']
                rows.append(item)
                # The homepage is deliberately capped, even when staff publish
                # more placements. Additional items remain in the media archive.
                if destination == 'foundation_home' and len(rows) == 3:
                    break
        response = Response({'items': rows, 'page': page,
                             'has_more': destination != 'foundation_home' and len(placements) > 200})
        response['Cache-Control'] = 'public, max-age=0, must-revalidate'
        return response


class PublicStudioAudioView(APIView):
    """Explicit public audio release; never reuses camper entitlement URLs."""
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @safe_media
    def get(self, request, asset_id):
        asset = get_object_or_404(StudioAsset, pk=asset_id, source_kind='recordings', archived_at__isnull=True)
        source = source_for(asset)
        if not source_published(asset, source) or source.session_id or not source.audio:
            raise Http404()
        if not StudioPlacement.objects.filter(
            asset=asset, destination='foundation_archive', edition__isnull=True,
            state='published', published_at__isnull=False,
        ).exists():
            raise Http404()
        suffix = Path(source.audio.name).suffix.lower()
        mime = {'.mp3': 'audio/mpeg', '.m4a': 'audio/mp4',
                '.wav': 'audio/wav', '.ogg': 'audio/ogg'}.get(suffix)
        if not mime:
            raise Http404()
        response = FileResponse(source.audio.open('rb'), content_type=mime,
                                as_attachment=request.query_params.get('download') == '1',
                                filename='foundation-audio' + suffix)
        return media_headers(response, public=True)
