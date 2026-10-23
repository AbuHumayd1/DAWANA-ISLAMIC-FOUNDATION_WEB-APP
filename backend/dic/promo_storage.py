"""Private MP4 uploads; image storage behavior remains unchanged."""
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from .memory_storage import PrivateMemoryStorage

MAX_VIDEO_BYTES = 100 * 1024 * 1024


def validate_mp4(value):
    if getattr(value, '_committed', False):
        return  # Existing objects were validated before their initial storage write.
    if not value or value.size > MAX_VIDEO_BYTES:
        raise ValidationError('Upload an MP4 of at most 100 MB.')
    executable = shutil.which(getattr(settings, 'DIC_FFPROBE_BINARY', 'ffprobe'))
    if not executable:
        raise ValidationError('Video uploads require ffprobe on the backend host.')
    try:
        value.seek(0)
        header = value.read(12)
        if len(header) != 12 or header[4:8] != b'ftyp':
            raise ValidationError('Upload a genuine MP4 file.')
        value.seek(0)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'upload.mp4')
            with open(path, 'wb') as output:
                written = 0
                for chunk in value.chunks():
                    written += len(chunk)
                    if written > MAX_VIDEO_BYTES:
                        raise ValidationError('Upload an MP4 of at most 100 MB.')
                    output.write(chunk)
            result = subprocess.run([executable, '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov', '-enable_drefs', '0',
                                     '-show_entries', 'stream=codec_type,codec_name:format=duration',
                                     '-of', 'json', path], capture_output=True, timeout=20, check=True)
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        if (not any(s.get('codec_type') == 'video' and s.get('codec_name') == 'h264' for s in streams)
                or any(s.get('codec_type') not in ('video', 'audio') or
                       s.get('codec_name') not in ('h264', 'aac') for s in streams)
                or not 0 < float(data['format']['duration']) <= 180):
            raise ValidationError('Use H.264 MP4, optional AAC audio, up to three minutes.')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise ValidationError('The MP4 could not be validated. Export a valid H.264/AAC MP4.') from None
    finally:
        value.seek(0)


class PrivatePromoStorage(PrivateMemoryStorage):
    def _save(self, name, content):
        validate_mp4(content)
        name = f'memories/promos/{uuid.uuid4().hex}.mp4'
        backend = self._backend()
        content.seek(0)
        if backend is not None:
            return backend.save(name, content)
        self._client().put_object(Bucket=settings.DIC_MEMORY_S3_BUCKET, Key=name, Body=content,
                                  ContentLength=content.size, ContentType='video/mp4', IfNoneMatch='*')
        return name


private_promo_storage = PrivatePromoStorage()
