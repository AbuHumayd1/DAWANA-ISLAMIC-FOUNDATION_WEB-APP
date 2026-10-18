import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone


def digest_value(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_order_access_token():
    return secrets.token_urlsafe(32)


def order_access_token_expiry():
    return timezone.now() + timedelta(days=30)
