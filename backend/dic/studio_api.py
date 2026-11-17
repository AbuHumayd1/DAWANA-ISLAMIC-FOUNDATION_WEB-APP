"""DAWANA Studio stage 1: independent staff login and audited media inventory.

This API never exposes private object keys, bucket details or draft media URLs.
It deliberately reuses existing models and session/CSRF infrastructure.
"""
from django.contrib.auth import authenticate, login, logout, get_user_model
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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .memory_models import CampPhotograph, CampVideo
from .promo_models import PromoVideo, CampFlyer
from .showcase_models import Lecturer, LecturerAppearance, CampActivity
from .camp_release_models import LectureRecording
from .models import DICAdminAuditEvent

LIBRARIES = {
    'photos': (CampPhotograph, 'campphotograph', 'caption'),
    'videos': (CampVideo, 'campvideo', 'caption'),
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
        rows = []
        for item in queryset[:101]:
            if len(rows) == 100:
                break
            label = str(getattr(item, title, '') or item)
            rows.append({'id': item.pk, 'title': label, 'state': getattr(item, 'state', 'reference'),
                         'edition': getattr(item, 'edition_id', None),
                         'updated_at': getattr(item, 'updated_at', None),
                         'featured': bool(getattr(item, 'featured', False)),
                         'preview_url': preview_route(item) if preview_route else None})
        return self.nocache({'library': kind, 'items': rows, 'limit': 100,
                             'has_more': queryset[:101].count() > 100,
                             'can_publish': bool(request.user.is_superuser or request.user.has_perm('dic.publish_' + codename))})


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
            except ModelValidationError as error:
                raise ValidationError({'detail': error.messages}) from error
            DICAdminAuditEvent.objects.create(
                actor=request.user, action='studio_media_' + action,
                target_type=model.__name__, target_id=str(item.pk),
                details={'library': kind})
        return self.nocache({'id': item.pk, 'state': item.state})
