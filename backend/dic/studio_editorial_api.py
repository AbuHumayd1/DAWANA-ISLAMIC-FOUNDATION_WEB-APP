"""Staff-authorised Foundation publishing with anonymous, publication-gated reads."""
from datetime import datetime

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction, models
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .media_delivery import safe_media, media_headers
from .models import DICAdminAuditEvent
from .studio_api import StudioView
from .studio_publication_models import StudioCollection, StudioPublication
from .video_providers import video_source
from .studio_notifications import notify_publication, config_ready
import os


def can_edit(user):
    return user.is_active and user.is_staff and (
        user.is_superuser or user.has_perm('dic.manage_studio_assets'))


def can_publish(user):
    return user.is_active and user.is_staff and (
        user.is_superuser or user.has_perm('dic.publish_studio_placements'))


def require_editor(user):
    if not can_edit(user):
        raise PermissionDenied('Media Studio catalogue management required.')


def require_publisher(user):
    if not can_publish(user):
        raise PermissionDenied('Media Studio publication approval required.')


def model_validate(instance):
    try:
        instance.full_clean()
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc


def numeric_id(raw):
    value = str(raw or '')
    if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 9 or int(value) <= 0:
        raise ValidationError({'id': 'Choose a valid publication or collection.'})
    return int(value)


def audit(user, action, type_name, pk):
    DICAdminAuditEvent.objects.create(
        actor=user, action=action, target_type=type_name,
        target_id=str(pk), details={})


def collection_data(row):
    return {'id': row.pk, 'title': row.title, 'slug': row.slug,
            'description': row.description, 'kind': row.kind,
            'is_public': row.is_public, 'display_order': row.display_order}


def publication_data(row, public=False):
    data = {'id': row.pk, 'kind': row.kind, 'collection_id': row.collection_id,
            'title': row.title, 'description': row.description,
            'body': row.body, 'season': row.season, 'episode': row.episode,
            'event_at': row.event_at.isoformat() if row.event_at else None,
            'live_state': row.live_state,
            'published_at': row.published_at.isoformat() if row.published_at else None,
            'video_url': row.video_url if row.video_url else '',
            'meeting_url': row.meeting_url if row.meeting_url else '',
            'has_document': bool(row.document)}
    if not public:
        data['state'] = row.state
        data['notification_sent'] = bool(row.notified_at)
    if row.video_url:
        try:
            data['embed_url'] = video_source(row.video_url)['embed_url']
        except ModelValidationError:
            data['embed_url'] = ''
    if public and row.kind == 'document' and row.document:
        data['document_url'] = '/api/v1/dic/studio/public-editorial/' + str(row.pk) + '/document/'
    return data


class EditorialCollectionsView(StudioView):
    def get(self, request):
        require_editor(request.user)
        rows = StudioCollection.objects.order_by('display_order', 'title')[:200]
        return self.nocache({'collections': [collection_data(row) for row in rows]})

    def post(self, request):
        require_editor(request.user)
        title = request.data.get('title', '')
        slug = request.data.get('slug', '')
        description = request.data.get('description', '')
        kind = request.data.get('kind', 'programme')
        if not all(isinstance(v, str) for v in (title, slug, description, kind)):
            raise ValidationError('Invalid collection fields.')
        collection = StudioCollection(
            title=title.strip(), slug=slug.strip().lower(),
            description=description.strip(), kind=kind,
            created_by=request.user)
        model_validate(collection)
        with transaction.atomic():
            collection.save()
            audit(request.user, 'studio_collection_created', 'StudioCollection', collection.pk)
        return self.nocache({'collection': collection_data(collection)}, status=201)


class EditorialCollectionDetailView(StudioView):
    def patch(self, request, collection_id):
        require_editor(request.user)
        data = request.data
        fields = {'title', 'slug', 'description', 'kind', 'display_order', 'is_public'}
        if not isinstance(data, dict) or not data or not set(data).issubset(fields):
            raise ValidationError('Invalid collection fields.')
        if 'is_public' in data:
            require_publisher(request.user)
        with transaction.atomic():
            collection = get_object_or_404(StudioCollection.objects.select_for_update(),
                                           pk=collection_id)
            for key, value in data.items():
                if key in ('title', 'slug', 'description', 'kind'):
                    if not isinstance(value, str):
                        raise ValidationError({key: 'Enter valid text.'})
                    value = value.strip()
                if key == 'display_order' and (not isinstance(value, int) or
                                               isinstance(value, bool) or not 0 <= value <= 10000):
                    raise ValidationError({key: 'Choose an order between 0 and 10000.'})
                if key == 'is_public' and not isinstance(value, bool):
                    raise ValidationError({key: 'Choose a visibility setting.'})
                setattr(collection, key, value)
            model_validate(collection)
            collection.save()
            audit(request.user, 'studio_collection_updated', 'StudioCollection', collection.pk)
        return self.nocache({'collection': collection_data(collection)})


EDITORIAL_FIELDS = frozenset({
    'kind', 'title', 'description', 'body', 'video_url', 'meeting_url', 'event_at',
    'live_state', 'collection_id', 'season', 'episode'})


def apply_fields(publication, data):
    allowed = EDITORIAL_FIELDS | {'document'}
    if not set(data).issubset(allowed):
        raise ValidationError('Unexpected editorial fields.')
    for field in EDITORIAL_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == 'collection_id':
            publication.collection_id = numeric_id(value) if value else None
        elif field in ('season', 'episode'):
            if not str(value).isascii() or not str(value).isdigit() or not 1 <= int(value) <= 999:
                raise ValidationError({field: 'Choose a number between 1 and 999.'})
            setattr(publication, field, int(value))
        elif field == 'event_at':
            if value in ('', None):
                publication.event_at = None
            else:
                if not isinstance(value, str):
                    raise ValidationError({field: 'Use an ISO date and time.'})
                try:
                    event_at = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if timezone.is_naive(event_at):
                        raise ValueError
                except ValueError:
                    raise ValidationError({field: 'Use a timezone-aware ISO date and time.'}) from None
                publication.event_at = event_at
        else:
            if not isinstance(value, str):
                raise ValidationError({field: 'Enter valid text.'})
            setattr(publication, field, value.strip())
    if 'document' in data:
        upload = data['document']
        if not getattr(upload, 'read', None):
            raise ValidationError({'document': 'Upload a PDF.'})
        publication.document = upload


class EditorialItemsView(StudioView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get(self, request):
        require_editor(request.user)
        rows = StudioPublication.objects.select_related('collection').order_by('-pk')[:200]
        return self.nocache({'items': [publication_data(x) for x in rows]})

    def post(self, request):
        require_editor(request.user)
        if not isinstance(request.data, dict) and not hasattr(request.data, 'keys'):
            raise ValidationError('Invalid publication.')
        item = StudioPublication(created_by=request.user, state='draft')
        apply_fields(item, request.data)
        model_validate(item)
        with transaction.atomic():
            item.save()
            audit(request.user, 'studio_publication_created', 'StudioPublication', item.pk)
        return self.nocache({'item': publication_data(item)}, status=201)


class EditorialItemDetailView(StudioView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def patch(self, request, item_id):
        require_editor(request.user)
        with transaction.atomic():
            item = get_object_or_404(StudioPublication.objects.select_for_update(),
                                     pk=item_id)
            if item.state == 'published':
                raise ValidationError('Withdraw the publication before editing.')
            apply_fields(item, request.data)
            model_validate(item)
            item.save()
            audit(request.user, 'studio_publication_updated', 'StudioPublication', item.pk)
        return self.nocache({'item': publication_data(item)})

    def post(self, request, item_id):
        require_publisher(request.user)
        action = request.data.get('action', '')
        if action not in ('publish', 'withdraw', 'notify'):
            raise ValidationError('Choose publish, withdraw or notify subscribers.')
        if action == 'notify':
            item = get_object_or_404(StudioPublication, pk=item_id, state='published')
            outcome = notify_publication(item.pk)
            return self.nocache({'item': publication_data(item), 'notification': outcome})
        with transaction.atomic():
            item = get_object_or_404(StudioPublication.objects.select_for_update(),
                                     pk=item_id)
            if action == 'publish':
                if item.state == 'published':
                    raise ValidationError('Already published. No duplicate publication.')
                item.state = 'published'
                item.published_at = timezone.now()
                item.notified_at = None
            else:
                item.state = 'withdrawn'
                item.published_at = None
                item.notified_at = None
            model_validate(item)
            item.save()
            audit(request.user, 'studio_publication_' + action,
                  'StudioPublication', item.pk)
        notification = notify_publication(item.pk) if action == 'publish' else 'not_sent'
        return self.nocache({'item': publication_data(item), 'notification': notification})


class PublicEditorialView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        group = request.query_params.get('collection', '')
        kinds = request.query_params.get('kind', '')
        if len(group) > 170 or len(kinds) > 20:
            raise ValidationError('Invalid collection filter.')
        try:
            page = numeric_id(request.query_params.get('page', 1))
        except ValidationError:
            raise ValidationError({'page': 'Choose a valid page.'}) from None
        if page > 100:
            raise ValidationError({'page': 'Page out of range.'})
        collections = list(StudioCollection.objects.filter(is_public=True).order_by(
            'display_order', 'title')[:200])
        visible = StudioPublication.objects.filter(
            state='published', published_at__isnull=False).filter(
            models.Q(collection__isnull=True) | models.Q(collection__is_public=True))
        if group:
            visible = visible.filter(collection__slug=group)
        if kinds:
            if kinds not in dict(StudioPublication._meta.get_field('kind').choices):
                raise ValidationError({'kind': 'Choose a supported media type.'})
            visible = visible.filter(kind=kinds)
        start = (page - 1) * 24
        items = list(visible.select_related('collection').order_by(
            '-published_at', '-pk')[start:start + 25])
        result = Response({'collections': [collection_data(x) for x in collections],
                           'items': [publication_data(x, public=True) for x in items[:24]],
                           'page': page, 'has_more': len(items) > 24})
        result['Cache-Control'] = 'public, max-age=0, must-revalidate'
        return result


class PublicEditorialDocumentView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @safe_media
    def get(self, request, item_id):
        item = get_object_or_404(StudioPublication.objects.select_related('collection'),
                                 pk=item_id, state='published',
                                 published_at__isnull=False, kind='document')
        if (item.collection_id and not item.collection.is_public) or not item.document:
            raise Http404()
        response = FileResponse(item.document.open('rb'), content_type='application/pdf',
                                as_attachment=True, filename='dawana-publication.pdf')
        return media_headers(response, public=True)


class PublicNotificationConfigView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        ready = config_ready()
        response = Response({'enabled': ready,
                             'app_id': os.environ.get('DAWANA_ONESIGNAL_APP_ID') if ready else None})
        response['Cache-Control'] = 'no-store'
        return response
