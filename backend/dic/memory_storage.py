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
    def _backend(self):
        mode = getattr(settings, "DIC_MEMORY_STORAGE", "disabled")
        if mode == "local" and settings.DEBUG:
            root = getattr(settings, "DIC_MEMORY_LOCAL_ROOT", Path(settings.BASE_DIR) / "media" / "private-memories")
            return FileSystemStorage(location=root, file_permissions_mode=0o600, directory_permissions_mode=0o700)
        if mode == "s3":
            return None
        raise ImproperlyConfigured("Configure private DIC photo storage before uploading; local storage is development-only.")

    def _client(self):
        import boto3
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
        result = self._client().get_object(Bucket=settings.DIC_MEMORY_S3_BUCKET, Key=name)
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
        name = f"memories/{uuid.uuid4().hex}.jpg"
        backend = self._backend()
        if backend is not None:
            return backend.save(name, ContentFile(output.getvalue()))
        self._client().put_object(Bucket=settings.DIC_MEMORY_S3_BUCKET, Key=name,
                                  Body=output.getvalue(), ContentType="image/jpeg")
        return name

    def exists(self, name):
        return False  # UUID object names; never overwrite an existing photo intentionally.

    def size(self, name):
        backend = self._backend()
        if backend is not None:
            return backend.size(name)
        return self._client().head_object(Bucket=settings.DIC_MEMORY_S3_BUCKET, Key=name)["ContentLength"]

    def url(self, name):
        raise ValueError("Private photographs are served only through authorized views.")


private_memory_storage = PrivateMemoryStorage()
