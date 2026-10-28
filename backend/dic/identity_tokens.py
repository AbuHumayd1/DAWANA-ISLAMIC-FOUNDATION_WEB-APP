"""Random QR credentials encrypted at rest; never encode participant data."""
import base64
import hashlib
import hmac
import secrets
from cryptography.fernet import Fernet
from django.conf import settings


def cipher():
    key = hmac.new(settings.SECRET_KEY.encode(), b'dawana-digital-id-qr-v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def digest(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def new_token():
    token = secrets.token_urlsafe(32)
    return digest(token), cipher().encrypt(token.encode('ascii')).decode('ascii')


def read_token(issue):
    return cipher().decrypt(issue.verification_secret.encode('ascii')).decode('ascii')
