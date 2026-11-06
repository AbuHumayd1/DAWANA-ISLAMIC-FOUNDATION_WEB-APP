"""Explicit maintenance primitive, never called by model signals or request saves."""
import re
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, models, transaction
from .memory_storage import PrivateMemoryStorage


def delete_unreferenced_object(storage, name, *, approved=False):
    if not approved or not getattr(settings, 'DIC_PRODUCTION_STORAGE', False):
        raise ValidationError('Deletion is production-only and requires explicit maintenance approval.')
    if not isinstance(storage, PrivateMemoryStorage) or not name or connection.vendor != 'postgresql':
        raise ValidationError('Unsupported object maintenance target.')
    bucket = storage._bucket()  # Exact approved production identity; never staging.
    pattern = (r'participants/portraits/[a-f0-9]{32}\.jpg' if storage.asset_kind == 'private'
        else r'memories/(?:[a-f0-9]{32}\.jpg|promos/[a-f0-9]{32}\.mp4)')
    if not re.fullmatch(pattern, name):
        raise ValidationError('Only application-generated object keys are eligible for maintenance.')
    fields = [(model, field) for model in apps.get_models() for field in model._meta.fields
        if isinstance(field, models.FileField) and isinstance(field.storage, PrivateMemoryStorage)
        and field.storage.asset_kind == storage.asset_kind]
    if not fields:
        raise ValidationError('No registered file-reference fields; deletion refused.')
    # Serialize against all ORM inserts/updates/deletes of file references. This
    # intentionally requires a reviewed maintenance window, not a web request.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            for table in sorted({model._meta.db_table for model, field in fields}):
                cursor.execute('LOCK TABLE ' + connection.ops.quote_name(table) + ' IN SHARE ROW EXCLUSIVE MODE')
        if any(model._base_manager.filter(**{field.name: name}).exists() for model, field in fields):
            raise ValidationError('Object is still referenced; deletion refused.')
        storage._client().delete_object(Bucket=bucket, Key=name)
    # Metadata is not deleted here. A provider failure raises; never record success.
