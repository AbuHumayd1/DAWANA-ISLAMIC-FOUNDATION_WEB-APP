"""Opt-in web push delivery via OneSignal, safely disabled until configured.

A failed provider request never rolls back a successfully approved publication.
Retries use a stable provider idempotency key per publication event.
"""
import logging
import os
import uuid

import requests
from django.db import transaction
from django.utils import timezone

from .models import DICAdminAuditEvent
from .studio_publication_models import StudioPublication

LOG = logging.getLogger(__name__)
URL = 'https://api.onesignal.com/notifications'


def config_ready():
    return bool(os.environ.get('DAWANA_ONESIGNAL_APP_ID') and
                os.environ.get('DAWANA_ONESIGNAL_API_KEY'))


def notification_url(item):
    category = ({'article': 'publications', 'document': 'publications',
                 'live': 'live', 'event': 'events', 'podcast': 'podcasts',
                 'video': 'videos'})[item.kind]
    if item.collection_id and item.collection.is_public:
        category = item.collection.slug
    return 'https://dawanaislamicfoundation.org/media?collection=' + category


def notify_public_placement(placement_id):
    """Optional event alert when a publicly approved legacy asset is released."""
    if not config_ready():
        return 'unconfigured'
    from .studio_models import StudioPlacement
    placement = StudioPlacement.objects.select_related('asset').filter(
        pk=placement_id, destination='foundation_archive', state='published',
        published_at__isnull=False, asset__archived_at__isnull=True).first()
    if not placement:
        return 'not_public'
    asset = placement.asset
    from .studio_catalogue_api import source_for, source_published, published_url
    source = source_for(asset)
    if not source_published(asset, source):
        return 'not_public'
    if asset.source_kind == 'recordings':
        if getattr(source, 'session_id', None) or not source.audio:
            return 'not_public'
    elif not published_url(asset, source):
        return 'not_public'
    category = asset.programme or ('audio' if asset.source_kind == 'recordings' else 'videos')
    from urllib.parse import urlencode
    destination = 'https://dawanaislamicfoundation.org/media?' + urlencode({'collection': category})
    key = str(uuid.uuid5(uuid.NAMESPACE_URL,
        'dawana-legacy-placement:' + str(placement.pk) + ':' + placement.published_at.isoformat()))
    try:
        response = requests.post(URL,
            headers={'Authorization': 'Key ' + os.environ['DAWANA_ONESIGNAL_API_KEY'],
                     'Content-Type': 'application/json'},
            json={'app_id': os.environ['DAWANA_ONESIGNAL_APP_ID'],
                  'included_segments': ['Subscribed Users'], 'target_channel': 'push',
                  'headings': {'en': asset.title[:140]},
                  'contents': {'en': (asset.description or 'New DAWANA media is available.')[:200]},
                  'url': destination, 'idempotency_key': key}, timeout=4)
        response.raise_for_status()
        if not response.json().get('id'):
            return 'error'
    except (requests.RequestException, ValueError, KeyError):
        LOG.warning('OneSignal legacy publication delivery failed for placement %s', placement_id)
        return 'error'
    DICAdminAuditEvent.objects.create(action='studio_placement_notification_sent',
        target_type='StudioPlacement', target_id=str(placement.pk),
        details={'channel': 'web_push', 'provider': 'onesignal'})
    return 'sent'


def notify_publication(item_id):
    """Returns sent/already_sent/unconfigured/error; only server has provider key."""
    if not config_ready():
        return 'unconfigured'
    item = StudioPublication.objects.select_related('collection').filter(
        pk=item_id, state='published', published_at__isnull=False).first()
    if not item or (item.collection_id and not item.collection.is_public):
        return 'not_public'
    if item.notified_at:
        return 'already_sent'
    idempotency = str(uuid.uuid5(uuid.NAMESPACE_URL,
        'dawana-published:' + str(item.pk) + ':' + item.published_at.isoformat()))
    try:
        response = requests.post(
            URL,
            headers={'Authorization': 'Key ' + os.environ['DAWANA_ONESIGNAL_API_KEY'],
                     'Content-Type': 'application/json'},
            json={
                'app_id': os.environ['DAWANA_ONESIGNAL_APP_ID'],
                'included_segments': ['Subscribed Users'],
                'target_channel': 'push',
                'headings': {'en': item.title[:140]},
                'contents': {'en': (item.description or 'A new DAWANA publication is available.')[:200]},
                'url': notification_url(item),
                'idempotency_key': idempotency,
            }, timeout=4)
        response.raise_for_status()
        body = response.json()
        if not body.get('id'):
            return 'error'
    except (requests.RequestException, ValueError, KeyError):
        LOG.warning('OneSignal publication delivery failed for editorial ID %s', item_id)
        return 'error'
    with transaction.atomic():
        updated = StudioPublication.objects.filter(pk=item.pk, notified_at__isnull=True,
            state='published', published_at=item.published_at).update(notified_at=timezone.now())
        if updated:
            DICAdminAuditEvent.objects.create(action='studio_publication_notification_sent',
                target_type='StudioPublication', target_id=str(item.pk),
                details={'channel': 'web_push', 'provider': 'onesignal'})
    return 'sent'
