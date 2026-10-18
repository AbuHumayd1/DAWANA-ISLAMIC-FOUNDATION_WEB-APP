import hashlib

from django.core import signing


def order_access_token(public_id):
    return signing.Signer(salt="dic.registration-order-access.v1").sign(
        str(public_id)
    )


def digest_value(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
