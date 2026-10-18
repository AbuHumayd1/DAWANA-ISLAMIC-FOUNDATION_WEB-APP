import hmac

from django.utils import timezone
from rest_framework.exceptions import NotFound

from .security import digest_value


def require_order_access(request, order):
    if (
        order.access_token_revoked_at is not None
        or order.access_token_expires_at <= timezone.now()
    ):
        raise NotFound("Order not found.")

    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise NotFound("Order not found.")
    if not hmac.compare_digest(
        order.access_token_digest,
        digest_value(token.strip()),
    ):
        raise NotFound("Order not found.")
    return order
