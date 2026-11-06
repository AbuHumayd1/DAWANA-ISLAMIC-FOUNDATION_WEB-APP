"""Only mocks and SimpleTestCase: no live storage or database access."""
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from corsheaders.middleware import CorsMiddleware
from .media_delivery import safe_media, media_chunks, PortraitUnavailable
from .memory_storage import PrivateMemoryStorage, PrivateParticipantStorage
from .promo_views import editorial_image, promo_stream, asset
from .showcase_views import showcase_image


class MediaCorrectionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_public_editorial_embedding_and_private_previews(self):
        for preview, policy in [(False, 'cross-origin'), (True, 'same-origin')]:
            request = self.factory.get('/?preview=1' if preview else '/', HTTP_ORIGIN='https://portal.example.test')
            field = Mock()
            field.open.return_value = BytesIO(b'synthetic')
            with patch('dic.promo_views.asset', return_value=NS(image=field)):
                response = editorial_image(request, 1, 'flyer')
            self.assertEqual(response['Cross-Origin-Resource-Policy'], policy)
            self.assertIn('no-store', response['Cache-Control'])
            response.close()

    def test_unauthorized_preview_never_resolves_object(self):
        request = self.factory.get('/?preview=1')
        request.user = NS(is_active=False, is_staff=False)
        model = Mock()
        with patch('dic.promo_views.get_object_or_404') as lookup:
            with self.assertRaises(Http404): asset(request, model, 1)
            lookup.assert_not_called()

    @override_settings(CORS_ALLOWED_ORIGINS=['https://portal.example.test'], CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_ALLOW_CREDENTIALS=True, CORS_URLS_REGEX=r'^/api/')
    def test_credentialed_cors_matches_exact_trusted_origin_only(self):
        middleware = CorsMiddleware(lambda request: HttpResponse('synthetic'))
        for origin, allowed in [('https://portal.example.test', True),
                ('https://portal.example.test.evil.invalid', False), ('https://other.example.test', False)]:
            response = middleware(self.factory.get('/api/v1/dic/editorial/', HTTP_ORIGIN=origin))
            self.assertEqual(response.has_header('Access-Control-Allow-Origin'), allowed)
            if allowed:
                self.assertEqual(response['Access-Control-Allow-Origin'], origin)
                self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')

    def test_expected_failures_have_sanitized_private_responses(self):
        failures = [(ImproperlyConfigured('sensitive-endpoint'), 503),
            (ValidationError('sensitive-key'), 503), (OSError('sensitive-path'), 503),
            (FileNotFoundError('sensitive-path'), 404),
            (ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'sensitive-key'}}, 'GetObject'), 404),
            (ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'sensitive-key'}}, 'GetObject'), 503)]
        for error, status in failures:
            with self.subTest(error=type(error).__name__):
                response = safe_media(Mock(side_effect=error))()
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b'sensitive', response.content)
                self.assertEqual(response['Cross-Origin-Resource-Policy'], 'same-origin')
                self.assertIn('no-store', response['Cache-Control'])

    def test_stream_failure_after_headers_terminates_and_logs_no_details(self):
        body = Mock()
        body.read.side_effect = [b'first', OSError('sensitive-provider-error')]
        with patch('dic.promo_views.asset') as lookup:
            storage = lookup.return_value.video.storage
            storage._backend.return_value = None
            storage._client.return_value.head_object.return_value = {'ContentLength': 10}
            storage._client.return_value.get_object.return_value = {'Body': body}
            response = promo_stream(self.factory.get('/'), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cross-Origin-Resource-Policy'], 'cross-origin')
        with self.assertLogs('dic.media_delivery', level='WARNING') as logs:
            self.assertEqual(b''.join(response.streaming_content), b'first')
        self.assertNotIn('sensitive', str(logs.output))
        self.assertEqual(response.status_code, 200)  # Headers cannot be replaced after streaming.
        body.close.assert_called()
        response.close()

    def test_truncated_stream_is_detected(self):
        with self.assertLogs('dic.media_delivery', level='WARNING'):
            self.assertEqual(list(media_chunks(BytesIO(b'x'), 2)), [b'x'])

    @override_settings(DIC_PRODUCTION_STORAGE=True, DIC_PORTRAIT_CUTOVER_VERIFIED=False)
    def test_unverified_cutover_blocks_before_storage_lookup(self):
        with patch.object(PrivateMemoryStorage, '_open') as lookup:
            with self.assertRaises(PortraitUnavailable): PrivateParticipantStorage()._open('memories/existing.jpg')
            lookup.assert_not_called()

    @override_settings(DIC_PRODUCTION_STORAGE=True, DIC_PORTRAIT_CUTOVER_VERIFIED=True)
    def test_missing_referenced_portrait_never_silently_succeeds_or_falls_back(self):
        from .identity_views import card_view, render_cards
        from .participant_api import PortalCardView
        from rest_framework.test import APIRequestFactory
        with patch.object(PrivateMemoryStorage, '_open', side_effect=FileNotFoundError('sensitive')) as lookup:
            with self.assertRaises(PortraitUnavailable): PrivateParticipantStorage()._open('memories/existing.jpg')
            lookup.assert_called_once_with('memories/existing.jpg', 'rb')
        with patch('dic.identity_views.require_staff'), patch('dic.identity_views.get_object_or_404'), \
                patch('dic.identity_views.card_context', side_effect=PortraitUnavailable()):
            request = self.factory.get('/')
            request.user = Mock()
            self.assertEqual(card_view(request, 'synthetic').status_code, 503)
            self.assertEqual(render_cards(request, [NS(pk=1)]).status_code, 503)
        with patch('dic.participant_api.authorized_portal_card', side_effect=PortraitUnavailable()):
            response = PortalCardView.as_view()(APIRequestFactory().get('/'), enrollment_id='synthetic')
            self.assertEqual(response.status_code, 503)


class ShowcaseVisibilityTests(SimpleTestCase):
    def request(self, preview=False, staff=False):
        request = RequestFactory().get('/?preview=1' if preview else '/')
        request.user = NS(is_active=staff, is_staff=staff, has_perm=lambda permission: staff)
        return request

    def retrieve(self, kind, *, active=True, published=True, preview=False, staff=False, previous=False):
        # Evaluate the actual route's queryset predicates against a synthetic row.
        query = Mock()
        query.filter.return_value = query
        query.exclude.return_value = query
        photograph = Mock()
        photograph.open.return_value = BytesIO(b'image')
        def lookup(selected, **kwargs):
            if not preview:
                filters = query.filter.call_args_list
                if not published and any(call.kwargs.get('state') == 'published' for call in filters):
                    raise Http404
                if not active:
                    if any(call.kwargs.get('edition__is_active') for call in filters): raise Http404
                    if not previous and any(call.args for call in filters): raise Http404
            return NS(photograph=photograph, lecturer=NS(photograph=photograph))
        module = 'dic.showcase_views.'
        model = 'LecturerAppearance' if kind == 'lecturer' else 'CampActivity'
        with patch(module + model + '.objects.all', return_value=query), \
                patch(module + 'get_object_or_404', side_effect=lookup):
            response = showcase_image(self.request(preview, staff), kind, 1)
        return response, photograph

    def test_active_published_images_allow_public_embedding(self):
        for kind in ('lecturer', 'activity'):
            response, _ = self.retrieve(kind)
            self.assertEqual(response['Cross-Origin-Resource-Policy'], 'cross-origin')
            response.close()

    def test_inactive_upcoming_and_activity_and_unpublished_images_are_rejected(self):
        for kind in ('lecturer', 'activity'):
            for kwargs in ({'active': False}, {'published': False}):
                with self.subTest(kind=kind, kwargs=kwargs), self.assertRaises(Http404):
                    self.retrieve(kind, **kwargs)

    def test_previous_edition_lecturer_remains_visible_as_in_listing(self):
        response, _ = self.retrieve('lecturer', active=False, previous=True)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_authorized_preview_can_open_inactive_draft_privately(self):
        response, _ = self.retrieve('activity', active=False, published=False, preview=True, staff=True)
        self.assertEqual(response['Cross-Origin-Resource-Policy'], 'same-origin')
        response.close()
        with self.assertRaises(Http404): self.retrieve('activity', preview=True)
