import json
import secrets
from hashlib import sha256
from django.db import connection
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import SimpleRateThrottle
from .identity_cards import card_context, require_staff, verify
from .models import CampEnrollment
from .participant_services import record
from .identity_branding import official_logo_data
from .media_delivery import safe_media

CARDS_PER_A4_PAGE = 8
PRINT_FORMATS = {
    'pvc': {'label': 'Standard PVC card', 'width': '85.6', 'height': '54', 'per_page': 8},
    'a6': {'label': 'Large A6 camp badge', 'width': '105', 'height': '148', 'per_page': 4},
}


def card_pages(cards, per_page=CARDS_PER_A4_PAGE):
    return [cards[start:start + per_page] for start in range(0, len(cards), per_page)]


def secured(response, nonce=None):
    response['Cache-Control'] = 'private, no-store'
    response['Cross-Origin-Resource-Policy'] = 'same-origin'
    response['Pragma'] = 'no-cache'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    if nonce:
        response['Content-Security-Policy'] = f"default-src 'none'; img-src data:; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    return response


@safe_media
def render_cards(request, enrollments, download=False, batch=False, card_format='pvc', printer='borderless'):
    require_staff(request.user)
    return _render_authorized_cards(request, enrollments, download, batch, card_format, printer)


def _render_authorized_cards(request, enrollments, download=False, batch=False, card_format='pvc', printer='borderless', portal=False):
    """Internal renderer: callers must establish staff or scoped portal authority."""
    from django.http import HttpResponseBadRequest
    if card_format not in PRINT_FORMATS or printer not in ('borderless', 'standard'):
        return secured(HttpResponseBadRequest('Unsupported identification format or printer layout.'))
    cards = []
    errors = []
    seen = set()
    for enrollment in enrollments:
        if enrollment.pk in seen:
            continue
        seen.add(enrollment.pk)
        try:
            cards.append(card_context(request, enrollment))
        except ValidationError:
            errors.append(enrollment.participant_number + (': no active eligible ID is available; please contact authorized DIC staff.'
                if portal else ': no active eligible QR card; review and issue first.'))
    nonce = secrets.token_urlsafe(18)
    batch = batch or len(cards) > 1
    per_page = 2 if card_format == 'a6' and printer == 'standard' else PRINT_FORMATS[card_format]['per_page']
    response = TemplateResponse(request, 'dic/identity_cards.html', dict(cards=cards, pages=card_pages(cards, per_page),
        batch=batch, portal=portal, card_format=card_format, format_info=PRINT_FORMATS[card_format], printer=printer,
        logo=official_logo_data(), errors=errors, nonce=nonce,
        demo=connection.settings_dict['NAME'].startswith('dawana_ids_demo_')))
    if download:
        response['Content-Disposition'] = 'attachment; filename="dawana-id-cards.html"'
    return secured(response, nonce)


@require_GET
@safe_media
def card_view(request, enrollment_id):
    require_staff(request.user)
    enrollment = get_object_or_404(CampEnrollment.objects.select_related('participant', 'edition', 'source_item'), pk=enrollment_id)
    if request.GET.get('format') == 'portrait':
        from .portrait_pdf import render_pdf, PDFUnavailable, require_pdf_dependencies
        from django.http import HttpResponse, HttpResponseBadRequest
        try:
            require_pdf_dependencies()
            payload = render_pdf([card_context(request, enrollment)])
        except ValidationError:
            return secured(HttpResponseBadRequest('No active eligible QR card is available. Review and issue first.'))
        except PDFUnavailable as error:
            return secured(HttpResponse(str(error.detail), status=503))
        response = HttpResponse(payload, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="dawana-portrait-id.pdf"'
        return secured(response)
    return render_cards(request, [enrollment], download=request.GET.get('download') == '1',
        batch=request.GET.get('layout') == 'batch', card_format=request.GET.get('format', 'pvc'),
        printer=request.GET.get('printer', 'borderless'))


class VerificationThrottle(SimpleRateThrottle):
    scope = 'dic_id_verification'
    rate = '30/min'

    def get_cache_key(self, request, view):
        # Ignore untrusted forwarded IP headers. No QR credentials in cache keys.
        return 'dic-qr-rate-' + sha256(request.META.get('REMOTE_ADDR', '').encode()).hexdigest()


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
def verify_view(request):
    if request.method == 'GET':
        nonce = secrets.token_urlsafe(18)
        return secured(TemplateResponse(request, 'dic/identity_verify.html', {'nonce': nonce}), nonce)
    throttle = VerificationThrottle()
    if not throttle.allow_request(request, None):
        response = JsonResponse({'status': 'unavailable', 'detail': 'Please wait before trying again.'}, status=429)
        response['Retry-After'] = str(max(1, int(throttle.wait() or 60)))
        return secured(response)
    try:
        if len(request.body) > 2048:
            raise ValueError
        body = json.loads(request.body)
        result = verify(body.get('token') if isinstance(body, dict) else None, request.user)
    except (ValueError, UnicodeDecodeError):
        result = None
    return secured(JsonResponse(result or {'status': 'unavailable', 'detail': 'This ID cannot be verified. Contact authorized staff.'}, status=200 if result else 404))
