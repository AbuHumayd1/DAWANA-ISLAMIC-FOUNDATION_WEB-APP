"""DAWANA Studio stage 1: independent staff login and audited media inventory.

This API never exposes private object keys, bucket details or draft media URLs.
It deliberately reuses existing models and session/CSRF infrastructure.
"""
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.conf import settings
from django.forms import modelform_factory
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.urls import reverse
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.cache import patch_cache_control
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .memory_models import CampPhotograph, CampVideo
from .promo_models import PromoVideo, CampFlyer
from .showcase_models import Lecturer, LecturerAppearance, CampActivity
from .camp_release_models import LectureRecording
from .studio_hosted_models import StudioHostedVideo
from .video_providers import video_source
from .models import DICAdminAuditEvent, CampEdition

def revoke_studio_placements(kind, source_id):
    """Explicit withdrawal or public content edits revoke every prior placement.

    A later source re-publication must never silently reinstate old destinations.
    """
    from .studio_models import StudioPlacement
    return StudioPlacement.objects.filter(
        asset__source_kind=kind, asset__source_id=source_id,
        state='published').update(state='withdrawn', published_at=None, published_by=None)


LIBRARIES = {
    'photos': (CampPhotograph, 'campphotograph', 'caption'),
    'videos': (CampVideo, 'campvideo', 'caption'),
    'hosted': (StudioHostedVideo, 'studiohostedvideo', 'title'),
    'recordings': (LectureRecording, 'lecturerecording', 'title'),
    'flyers': (CampFlyer, 'campflyer', 'title'),
    'promotions': (PromoVideo, 'promovideo', 'title'),
    'lecturers': (Lecturer, 'lecturer', 'name'),
    'appearances': (LecturerAppearance, 'lecturerappearance', 'topic'),
    'activities': (CampActivity, 'campactivity', 'title'),
}
VIEW_GRANTS = tuple('dic.view_' + model for _, model, _ in LIBRARIES.values())
ACTION_GRANTS = ('dic.publish_campphotograph', 'dic.publish_campvideo',
                 'dic.publish_lecturerecording', 'dic.publish_campflyer',
                 'dic.publish_promovideo', 'dic.publish_campactivity')


def studio_allowed(user):
    return bool(user is not None and user.is_authenticated and user.is_active and user.is_staff
                and (user.is_superuser or any(user.has_perm(p) for p in VIEW_GRANTS)))


def profile(user):
    return {'display_name': user.get_full_name() or user.get_username(),
            'username': user.get_username(),
            'owner': bool(user.is_superuser),
            'libraries': [key for key, (_, model, _) in LIBRARIES.items()
                          if user.is_superuser or user.has_perm('dic.view_' + model)],
            'can_publish': {key: bool(user.is_superuser or user.has_perm('dic.publish_' + model))
                            for key, (_, model, _) in LIBRARIES.items()}}


@ensure_csrf_cookie
@require_GET
def studio_csrf(request):
    response = JsonResponse({'csrfToken': get_token(request)})
    response['Cache-Control'] = 'no-store'
    return response


class StudioLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'dic_ops_login'

    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        username, password = request.data.get('username', ''), request.data.get('password', '')
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 150 or len(password) > 1024:
            return Response({'detail': 'Invalid username or password.'}, status=400)
        user = authenticate(request=request, username=username, password=password)
        if user is None and '@' in username:
            matches = get_user_model().objects.filter(email__iexact=username, is_active=True)
            if matches.count() == 1:
                user = authenticate(request=request, username=matches.get().get_username(), password=password)
        if not studio_allowed(user):
            return Response({'detail': 'Invalid username or password.'}, status=401)
        login(request, user)
        response = Response(profile(user))
        response['Cache-Control'] = 'no-store'
        return response


class StudioView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not studio_allowed(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Media Studio staff access required.')

    @staticmethod
    def nocache(data, **kwargs):
        response = Response(data, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class StudioMeView(StudioView):
    def get(self, request):
        return self.nocache(profile(request.user))


class StudioLogoutView(StudioView):
    def post(self, request):
        logout(request)
        return self.nocache({}, status=204)


def safe_studio_player(url):
    """Never leak unapproved host links; a withdrawn provider should not break inventory."""
    from django.core.exceptions import ValidationError
    try:
        return video_source(url)['embed_url']
    except ValidationError:
        return None


class StudioLibraryView(StudioView):
    def get(self, request):
        from rest_framework.exceptions import PermissionDenied, ValidationError
        from django.db.models import Q
        kind = request.query_params.get('library', 'photos')
        if kind not in LIBRARIES:
            raise ValidationError({'library': 'Choose an available media library.'})
        model, codename, title = LIBRARIES[kind]
        if not request.user.is_superuser and not request.user.has_perm('dic.view_' + codename):
            raise PermissionDenied('Library permission required.')
        queryset = model.objects.all().order_by('-pk')
        term = request.query_params.get('q', '').strip()
        if len(term) > 100:
            raise ValidationError({'q': 'Search is limited to 100 characters.'})
        if term:
            queryset = queryset.filter(**{title + '__icontains': term})
        state = request.query_params.get('state', '')
        if state:
            if state not in ('draft', 'review', 'published', 'archived') or not any(f.name == 'state' for f in model._meta.fields):
                raise ValidationError({'state': 'Choose a valid editorial state.'})
            queryset = queryset.filter(state=state)
        edition = request.query_params.get('edition', '')
        if edition:
            if not edition.isascii() or not edition.isdigit() or not 0 < len(edition) <= 9:
                raise ValidationError({'edition': 'Invalid edition.'})
            if not any(f.name == 'edition' for f in model._meta.fields):
                raise ValidationError({'edition': 'This library does not use camp editions.'})
            queryset = queryset.filter(edition_id=int(edition))
        preview_route = {
            'photos': lambda item: reverse('dic:memory-image', args=[item.pk]) + '?preview=1',
            'videos': lambda item: reverse('dic:video-thumbnail', args=[item.pk]) + '?preview=1' if item.thumbnail else None,
            'flyers': lambda item: reverse('dic:official-flyer', args=[item.pk]) + '?preview=1',
            'promotions': lambda item: reverse('dic:promo-poster', args=[item.pk]) + '?preview=1',
            'lecturers': lambda item: reverse('dic:showcase-image', args=['identity', item.pk]) if item.photograph else None,
            'appearances': lambda item: reverse('dic:showcase-image', args=['lecturer', item.pk]) + '?preview=1' if item.lecturer.photograph else None,
            'activities': lambda item: reverse('dic:showcase-image', args=['activity', item.pk]) + '?preview=1' if item.photograph else None,
        }.get(kind)
        if kind == 'appearances':
            queryset = queryset.select_related('lecturer')
        raw_page = request.query_params.get('page', '1')
        if not raw_page.isascii() or not raw_page.isdigit() or len(raw_page) > 3:
            raise ValidationError({'page': 'Choose a valid library page.'})
        page = int(raw_page)
        if not 1 <= page <= 100:
            raise ValidationError({'page': 'Library page out of range.'})
        offset = (page - 1) * 30
        records = list(queryset[offset:offset + 31])
        rows = []
        for item in records[:30]:
            label = str(getattr(item, title, '') or item)
            rows.append({'id': item.pk, 'title': label, 'state': getattr(item, 'state', 'reference'),
                         'edition': getattr(item, 'edition_id', None),
                         'updated_at': getattr(item, 'updated_at', None),
                         'featured': bool(getattr(item, 'featured', False)),
                         'preview_url': preview_route(item) if preview_route else None,
                         'player_url': safe_studio_player(item.video_url) if kind == 'hosted' else None,
                         'metadata': {name: getattr(item, name) for name in EDIT_FIELDS.get(kind, ())}})
        return self.nocache({'library': kind, 'items': rows, 'limit': 30, 'page': page,
                             'has_more': len(records) > 30,
                             'can_publish': bool(request.user.is_superuser or request.user.has_perm('dic.publish_' + codename)),
                             'can_edit': bool(request.user.is_superuser or request.user.has_perm('dic.change_' + codename)),
                             'can_create': bool(request.user.is_superuser or request.user.has_perm('dic.add_' + codename))})


class StudioPublicationView(StudioView):
    """One staff publisher publishes or withdraws existing editorial objects, with audit."""
    def post(self, request, kind, pk):
        from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
        if kind not in LIBRARIES or kind in ('lecturers', 'appearances'):
            raise NotFound('Unknown publishable Studio library.')
        model, code, _ = LIBRARIES[kind]
        if not (request.user.is_superuser or (
            request.user.has_perm('dic.change_' + code)
            and request.user.has_perm('dic.publish_' + code))):
            raise PermissionDenied('Media publishing permission required.')
        action = request.data.get('action')
        if action not in ('publish', 'withdraw'):
            raise ValidationError({'action': 'Choose publish or withdraw.'})
        from django.core.exceptions import ValidationError as ModelValidationError
        with transaction.atomic():
            item = model.objects.select_for_update().filter(pk=pk).first()
            if item is None:
                raise NotFound('Media item does not exist.')
            item.state = 'published' if action == 'publish' else 'draft'
            try:
                item.full_clean()
                item.save(actor=request.user)
                if action == 'withdraw':
                    revoke_studio_placements(kind, item.pk)
            except ModelValidationError as error:
                raise ValidationError({'detail': error.messages}) from error
            DICAdminAuditEvent.objects.create(
                actor=request.user, action='studio_media_' + action,
                target_type=model.__name__, target_id=str(item.pk),
                details={'library': kind})
        return self.nocache({'id': item.pk, 'state': item.state})


# Existing, schema-backed editorial media types; no generic arbitrary-key upload.
# Safe metadata only: no object keys, owner-only settings or media re-association.
EDIT_FIELDS = {
    'photos': ('caption', 'alt_text', 'featured', 'display_order'),
    'videos': ('caption', 'alt_text', 'lecturer', 'description', 'featured', 'display_order'),
    'hosted': ('title', 'lecturer', 'description'),
    'recordings': ('title', 'lecturer', 'description'),
    'flyers': ('title', 'alt_text', 'featured', 'display_order'),
    'promotions': ('title', 'description', 'alt_text', 'featured', 'display_order'),
    'lecturers': ('name', 'designation', 'biography', 'alt_text'),
    'activities': ('title', 'description', 'category', 'featured', 'display_order'),
}

UPLOAD_FIELDS = {
    'photos': ('edition', 'caption', 'alt_text', 'photograph'),
    'videos': ('edition', 'caption', 'alt_text', 'thumbnail', 'recording_file', 'lecturer', 'description'),
    'recordings': ('edition', 'title', 'lecturer', 'description', 'audio'),
    'flyers': ('edition', 'title', 'alt_text', 'image'),
    'promotions': ('edition', 'kind', 'source_edition', 'title', 'description', 'poster', 'video', 'alt_text'),
    'lecturers': ('name', 'photograph', 'alt_text', 'biography', 'designation'),
    'activities': ('edition', 'title', 'description', 'category', 'photograph', 'alt_text'),
}


def upload_enabled():
    """Feature is closed unless the owner explicitly enables production uploads."""
    if not getattr(settings, 'DIC_MEDIA_STUDIO_UPLOADS_ENABLED', False):
        return False
    if not getattr(settings, 'DIC_PRODUCTION_STORAGE', False) or getattr(settings, 'DIC_MEMORY_STORAGE', '') != 's3':
        return False
    try:
        from .memory_storage import private_memory_storage
        private_memory_storage._backend()  # Validates production R2 configuration; no network.
    except ImproperlyConfigured:
        return False
    return True


class StudioUploadView(StudioView):
    """Uploads save as drafts. They cannot self-publish or supply arbitrary file keys."""
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        return self.nocache({'enabled': upload_enabled(), 'libraries': list(UPLOAD_FIELDS),
                             'editions': list(CampEdition.objects.order_by('-year').values('id', 'name', 'year')[:30])})

    def post(self, request):
        from rest_framework.exceptions import PermissionDenied, ValidationError
        if not upload_enabled():
            return self.nocache({'detail': 'Media uploads await owner-approved R2 activation.'},
                                status=503)
        kind = request.data.get('library', '')
        if kind not in UPLOAD_FIELDS:
            raise ValidationError({'library': 'Choose a supported upload library.'})
        model, codename, _ = LIBRARIES[kind]
        if not request.user.is_superuser and not request.user.has_perm('dic.add_' + codename):
            raise PermissionDenied('Permission to create media is required.')
        UploadForm = modelform_factory(model, fields=UPLOAD_FIELDS[kind])
        form = UploadForm(request.data, request.FILES)
        if not form.is_valid():
            return self.nocache({'errors': {key: list(values) for key, values in form.errors.items()}},
                                status=400)
        with transaction.atomic():
            item = form.save(commit=False)
            if hasattr(item, 'state'):
                item.state = 'draft'
            item.save(actor=request.user) if hasattr(item, 'state') else item.save()
            form.save_m2m()
            DICAdminAuditEvent.objects.create(actor=request.user, action='studio_media_draft_uploaded',
                target_type=model.__name__, target_id=str(item.pk), details={'library': kind})
        return self.nocache({'id': item.pk, 'state': getattr(item, 'state', 'reference')}, status=201)


class StudioMetadataView(StudioView):
    """Update approved metadata only, withdrawing publication before any public edit."""
    def patch(self, request, kind, pk):
        from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
        from django.core.exceptions import ValidationError as ModelValidationError
        if kind not in EDIT_FIELDS:
            raise NotFound('Unknown editable media library.')
        model, codename, _ = LIBRARIES[kind]
        if not (request.user.is_superuser or request.user.has_perm('dic.change_' + codename)):
            raise PermissionDenied('Media editing permission required.')
        if not isinstance(request.data, dict) or not request.data:
            raise ValidationError({'detail': 'Choose media fields to change.'})
        if not set(request.data).issubset(EDIT_FIELDS[kind]):
            raise ValidationError({'detail': 'Only approved descriptive metadata can be edited.'})
        with transaction.atomic():
            item = model.objects.select_for_update().filter(pk=pk).first()
            if not item:
                raise NotFound('Media item does not exist.')
            old_state = getattr(item, 'state', 'reference')
            if hasattr(item, 'state') and item.state == 'published':
                item.state = 'draft'
            for name, value in request.data.items():
                field = model._meta.get_field(name)
                if field.get_internal_type() == 'BooleanField':
                    if not isinstance(value, bool):
                        raise ValidationError({name: 'Choose true or false.'})
                elif field.get_internal_type() == 'PositiveIntegerField':
                    if type(value) is not int or value < 0 or value > 1000000:
                        raise ValidationError({name: 'Choose a nonnegative display order.'})
                elif not isinstance(value, str):
                    raise ValidationError({name: 'Provide text.'})
                setattr(item, name, value)
            try:
                item.full_clean()
                if hasattr(item, 'state'):
                    item.save(actor=request.user)
                    if old_state == 'published':
                        revoke_studio_placements(kind, item.pk)
                else:
                    item.save()
            except ModelValidationError as error:
                raise ValidationError({'detail': error.messages}) from error
            DICAdminAuditEvent.objects.create(actor=request.user, action='studio_media_metadata_updated',
                target_type=model.__name__, target_id=str(item.pk),
                details={'library': kind, 'fields': sorted(request.data), 'previous_state': old_state,
                         'resulting_state': getattr(item, 'state', 'reference')})
        return self.nocache({'id': item.pk, 'state': getattr(item, 'state', 'reference'),
                             'metadata': {name: getattr(item, name) for name in EDIT_FIELDS[kind]}})


class StudioHostedLinksView(StudioView):
    """Create link-only YouTube/Vimeo draft records; no R2 setup or binary upload needed."""
    def post(self, request):
        from rest_framework.exceptions import PermissionDenied, ValidationError
        from .studio_models import StudioAsset
        if not (request.user.is_superuser or request.user.has_perm('dic.add_studiohostedvideo')):
            raise PermissionDenied('Media link creation permission required.')
        if not isinstance(request.data, dict):
            raise ValidationError({'detail': 'Supply video links and editorial details.'})
        entries = request.data.get('items', [])
        if not isinstance(entries, list) or not 1 <= len(entries) <= 25:
            raise ValidationError({'items': 'Supply between 1 and 25 hosted videos.'})
        allowed = {'title', 'video_url', 'lecturer', 'description', 'edition'}
        prepared = []
        Form = modelform_factory(StudioHostedVideo, fields=tuple(allowed))
        for index, values in enumerate(entries):
            if not isinstance(values, dict) or not set(values).issubset(allowed):
                raise ValidationError({'items': {str(index): 'Unsupported video fields.'}})
            form = Form(values)
            if not form.is_valid():
                raise ValidationError({'items': {str(index): form.errors.get_json_data()}})
            prepared.append(form)
        with transaction.atomic():
            output = []
            for form in prepared:
                record = form.save(commit=False)
                record.state = 'draft'
                record.save()
                asset = StudioAsset.objects.create(
                    source_kind='hosted', source_id=record.pk,
                    title=record.title, description=record.description, created_by=request.user)
                DICAdminAuditEvent.objects.create(
                    actor=request.user, action='studio_hosted_link_created',
                    target_type='StudioAsset', target_id=str(asset.pk),
                    details={'source_id': record.pk, 'provider': 'validated', 'state': 'draft'})
                output.append({'id': record.pk, 'asset_id': str(asset.pk), 'state': 'draft'})
        return self.nocache({'items': output}, status=201)
