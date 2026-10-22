"""Strict hosted-video parsing. No user supplied HTML or remote fetches."""
import re
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def video_source(value):
    try:
        if not isinstance(value, str) or len(value) > 500 or any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
            raise ValueError
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port or url.fragment:
            raise ValueError
        host = url.hostname
        video_id = None
        if host in ("youtube.com", "www.youtube.com", "youtu.be", "www.youtube-nocookie.com"):
            provider = "youtube"
            if host == "youtu.be":
                video_id = url.path.removeprefix("/")
            elif url.path == "/watch":
                values = parse_qs(url.query, keep_blank_values=True).get("v", [])
                video_id = values[0] if len(values) == 1 else None
            else:
                match = re.fullmatch(r"/(?:embed|shorts)/([A-Za-z0-9_-]{11})/?", url.path)
                video_id = match.group(1) if match else None
            if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                raise ValueError
            embed = f"https://www.youtube-nocookie.com/embed/{video_id}?playsinline=1"
        elif host in ("vimeo.com", "www.vimeo.com", "player.vimeo.com"):
            provider = "vimeo"
            pattern = r"/video/([1-9][0-9]{0,11})/?" if host == "player.vimeo.com" else r"/([1-9][0-9]{0,11})/?"
            match = re.fullmatch(pattern, url.path)
            if not match:
                raise ValueError
            video_id = match.group(1)
            embed = f"https://player.vimeo.com/video/{video_id}?dnt=1"
        else:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Enter a supported HTTPS video link without credentials, fragments or custom ports.") from None
    if provider not in getattr(settings, "DIC_VIDEO_APPROVED_PROVIDERS", []):
        raise ValidationError("This video provider has not been approved. Contact an administrator.")
    return {"provider": provider, "embed_url": embed}
