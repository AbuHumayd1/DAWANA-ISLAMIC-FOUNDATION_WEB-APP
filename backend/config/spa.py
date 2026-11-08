from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe


def validate_frontend(root):
    if not (root / 'index.html').is_file():
        raise RuntimeError('Build the Vite frontend before starting the native service.')
    for reserved in ('api', 'admin', 'static', 'media', 'health', '_container'):
        if (root / reserved).exists():
            raise RuntimeError('Frontend output must not shadow a reserved backend namespace.')


def static_headers(headers, path, url):
    headers['X-Frame-Options'] = 'DENY'
    if path.endswith('.html'):
        headers['Cache-Control'] = 'no-store'


@require_safe
def frontend(request, path=''):
    if '.' in path.rsplit('/', 1)[-1] or path.startswith('assets/'):
        raise Http404
    try:
        response = FileResponse((settings.FRONTEND_ROOT / 'index.html').open('rb'), content_type='text/html')
    except FileNotFoundError:
        raise Http404 from None
    response['Cache-Control'] = 'no-store'
    return response
