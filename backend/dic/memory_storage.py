"""Private photo storage. No filesystem or object URLs are publicly exposed."""
import io
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageOps, UnidentifiedImageError


def validate_photo(value):
    was_closed = getattr(value, "closed", False)
    if value.size > 12 * 1024 * 1024:
        raise ValidationError("Photographs must be no larger than 12 MB.")
    try:
        value.seek(0)
        with Image.open(value) as photo:
            if photo.format not in ("JPEG", "PNG", "WEBP"):
                raise ValidationError("Upload a JPEG, PNG or WebP photograph.")
            if photo.width * photo.height > 20_000_000 or getattr(photo, "n_frames", 1) != 1:
                raise ValidationError("Upload a still photograph of at most 20 megapixels.")
            photo.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("The photograph could not be validated.") from exc
    finally:
        value.seek(0)
        if was_closed:
            value.close()


@deconstructible
class PrivateMemoryStorage(Storage):
    asset_kind = 'media'

    def _bucket(self):
        if getattr(settings, 'DIC_PRODUCTION_STORAGE', False):
            from .storage_configuration import production_storage
            return production_storage(settings, self.asset_kind)['bucket']
        return settings.DIC_MEMORY_S3_BUCKET

    def _backend(self):
        mode = getattr(settings, "DIC_MEMORY_STORAGE", "disabled")
        if mode == "local" and settings.DEBUG:
            root = getattr(settings, "DIC_MEMORY_LOCAL_ROOT", Path(settings.BASE_DIR) / "media" / "private-memories")
            return FileSystemStorage(location=root, file_permissions_mode=0o600, directory_permissions_mode=0o700)
        if mode == "s3":
            self._bucket()  # Validate before any production SDK call.
            return None
        raise ImproperlyConfigured("Configure private DIC photo storage before uploading; local storage is development-only.")

    def _client(self):
        import boto3
        if getattr(settings, 'DIC_PRODUCTION_STORAGE', False):
            from .storage_configuration import production_storage
            from botocore.config import Config
            options = production_storage(settings, self.asset_kind)
            options.pop('bucket')
            return boto3.client('s3', **options, config=Config(connect_timeout=5, read_timeout=30,
                retries={'mode': 'standard', 'total_max_attempts': 2}))
        endpoint = getattr(settings, "DIC_MEMORY_S3_ENDPOINT", "")
        if endpoint and not endpoint.startswith("https://"):
            raise ImproperlyConfigured("Photo object storage requires HTTPS.")
        if not getattr(settings, "DIC_MEMORY_S3_BUCKET", ""):
            raise ImproperlyConfigured("Configure the private photo bucket.")
        return boto3.client("s3", endpoint_url=endpoint or None,
                            region_name=getattr(settings, "DIC_MEMORY_S3_REGION", "us-east-1"))

    def _open(self, name, mode="rb"):
        backend = self._backend()
        if backend is not None:
            return backend.open(name, mode)
        result = self._client().get_object(Bucket=self._bucket(), Key=name)
        body = result["Body"]
        try:
            data = body.read(12 * 1024 * 1024 + 1)
        finally:
            body.close()
        if len(data) > 12 * 1024 * 1024:
            raise ValidationError("Stored photograph exceeds the size limit.")
        return File(io.BytesIO(data), name=name)

    def _save(self, name, content):
        validate_photo(content)
        with Image.open(content) as source:
            photo = ImageOps.exif_transpose(source).convert("RGB")
            photo.thumbnail((2400, 2400))
            output = io.BytesIO()
            photo.save(output, format="JPEG", quality=88)
        # Re-encoding strips metadata, active payloads and user-supplied filenames.
        prefix = 'participants/portraits' if self.asset_kind == 'private' and getattr(settings, 'DIC_PRODUCTION_STORAGE', False) else 'memories'
        name = f"{prefix}/{uuid.uuid4().hex}.jpg"
        backend = self._backend()
        if backend is not None:
            return backend.save(name, ContentFile(output.getvalue()))
        options = {'IfNoneMatch': '*'} if getattr(settings, 'DIC_PRODUCTION_STORAGE', False) else {}
        self._client().put_object(Bucket=self._bucket(), Key=name,
                                  Body=output.getvalue(), ContentType="image/jpeg", **options)
        self._verify_upload(name, len(output.getvalue()))
        return name

    def _verify_upload(self, name, size):
        if getattr(settings, 'DIC_PRODUCTION_STORAGE', False):
            result = self._client().head_object(Bucket=self._bucket(), Key=name)
            if result.get('ContentLength') != size:
                raise ValidationError('Uploaded object could not be verified. The previous object is retained.')

    def delete(self, name):
        raise ValidationError('Object deletion requires separately approved unreferenced-object maintenance.')

    def exists(self, name):
        return False  # UUID object names; never overwrite an existing photo intentionally.

    def size(self, name):
        backend = self._backend()
        if backend is not None:
            return backend.size(name)
        return self._client().head_object(Bucket=self._bucket(), Key=name)["ContentLength"]

    def url(self, name):
        raise ValueError("Private photographs are served only through authorized views.")


private_memory_storage = PrivateMemoryStorage()


@deconstructible
class PrivateParticipantStorage(PrivateMemoryStorage):
    asset_kind = 'private'

    def _open(self, name, mode='rb'):
        if not getattr(settings, 'DIC_PRODUCTION_STORAGE', False):
            return super()._open(name, mode)
        from .media_delivery import PortraitUnavailable
        from botocore.exceptions import BotoCoreError, ClientError
        if not getattr(settings, 'DIC_PORTRAIT_CUTOVER_VERIFIED', False):
            raise PortraitUnavailable('Portrait cutover verification is required.')
        try:
            return super()._open(name, mode)
        except (FileNotFoundError, OSError, ImproperlyConfigured, ValidationError, BotoCoreError, ClientError):
            # Never retry editorial/staging storage or silently render a blank portrait.
            raise PortraitUnavailable('Referenced portrait is unavailable.') from None


private_participant_storage = PrivateParticipantStorage()
