"""Withdraw only the verified redundant public DIC'26 flyer highlight placement.

The original CampFlyer publication and its R2 artwork remain untouched.
The Foundation archive and other media placements are never modified.
"""
from uuid import UUID
from django.db import migrations


def withdraw_verified_duplicate(apps, schema_editor):
    Asset = apps.get_model('dic', 'StudioAsset')
    Placement = apps.get_model('dic', 'StudioPlacement')
    asset_id = UUID('4613b779-5f1a-4a4d-976e-e9fbf1dca914')
    if not Asset.objects.filter(
        id=asset_id, source_kind='flyers', source_id=1, title="DIC'26 FLYER",
        archived_at__isnull=True,
    ).exists():
        return
    Placement.objects.filter(
        asset_id=asset_id, destination='dic_landing',
        edition_id=1, state='published',
    ).update(state='withdrawn', published_at=None, published_by=None)


class Migration(migrations.Migration):
    dependencies = [('dic', '0045_studio_hosted_video')]
    operations = [migrations.RunPython(withdraw_verified_duplicate, migrations.RunPython.noop)]
