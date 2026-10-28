"""Embed the existing official website asset; no network requests while rendering."""
import base64
import io
from pathlib import Path
from django.conf import settings
from PIL import Image, UnidentifiedImageError

LOGO_FILE = Path(__file__).parent / 'static' / 'dic' / 'dawana-official-logo.img'


def official_logo_data():
    try:
        data = Path(getattr(settings, 'DIC_ID_LOGO_FILE', LOGO_FILE)).read_bytes()
        if len(data) > 2 * 1024 * 1024:
            return None
        with Image.open(io.BytesIO(data)) as image:
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}.get(image.format)
            image.verify()
        return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii') if mime else None
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None
