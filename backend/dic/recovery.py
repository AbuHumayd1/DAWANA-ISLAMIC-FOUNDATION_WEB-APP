import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string


logger = logging.getLogger(__name__)


class RecoveryDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class RecoveryChannel:
    key: str
    label: str
    available: bool


def recovery_encryption_configured():
    key = getattr(settings, "DIC_RECOVERY_ENCRYPTION_KEY", "")
    if not key:
        return False
    try:
        Fernet(key.encode("ascii"))
    except (AttributeError, UnicodeEncodeError, ValueError):
        return False
    return True


def _recovery_cipher():
    key = getattr(settings, "DIC_RECOVERY_ENCRYPTION_KEY", "")
    try:
        return Fernet(key.encode("ascii"))
    except (AttributeError, UnicodeEncodeError, ValueError) as exc:
        raise RecoveryDeliveryError(
            "Recovery delivery encryption is not configured."
        ) from exc


def encrypt_delivery_payload(channel, destination, code):
    payload = json.dumps(
        {"channel": channel, "destination": destination, "code": code},
        separators=(",", ":"),
    ).encode("utf-8")
    return _recovery_cipher().encrypt(payload).decode("ascii")


def decrypt_delivery_payload(encrypted_payload):
    try:
        payload = _recovery_cipher().decrypt(encrypted_payload.encode("ascii"))
        value = json.loads(payload)
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
        raise RecoveryDeliveryError("Recovery delivery payload is invalid.") from exc
    if (
        not isinstance(value, dict)
        or value.get("channel") not in ("email", "sms", "whatsapp")
        or not isinstance(value.get("destination"), str)
        or not isinstance(value.get("code"), str)
    ):
        raise RecoveryDeliveryError("Recovery delivery payload is invalid.")
    return value


def normalize_email(value):
    return value.strip().lower()


def normalize_phone(value):
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise ValueError("Enter a valid phone number.")
    if digits.startswith("2340") and len(digits) == 14:
        return f"+234{digits[4:]}"
    if digits.startswith("234") and len(digits) == 13:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+234{digits[1:]}"
    if len(digits) == 10:
        return f"+234{digits}"
    if raw.startswith("+"):
        return f"+{digits}"
    raise ValueError("Enter a valid phone number.")


def phone_match_digits(value):
    digits = re.sub(r"\D", "", value)
    if digits.startswith("2340") and len(digits) == 14:
        digits = f"234{digits[4:]}"
    if digits.startswith("234") and len(digits) == 13:
        national = digits[3:]
        return {digits, f"0{national}", national}
    if digits.startswith("0") and len(digits) == 11:
        return {f"234{digits[1:]}", digits, digits[1:]}
    return {digits}


def channel_available(channel):
    if not getattr(settings, "DIC_RECOVERY_DELIVERY_WORKER_ENABLED", False):
        return False
    if not recovery_encryption_configured():
        return False
    if channel == "email":
        backend = settings.EMAIL_BACKEND.lower()
        if not getattr(settings, "DIC_EMAIL_RECOVERY_ENABLED", False):
            return False
        if not getattr(settings, "DEFAULT_FROM_EMAIL", "").strip():
            return False
        if backend.endswith(("console.emailbackend", "locmem.emailbackend")):
            return False
        if backend.endswith("smtp.emailbackend") and not settings.EMAIL_HOST:
            return False
        return True
    if channel == "sms":
        return bool(getattr(settings, "DIC_SMS_RECOVERY_ADAPTER", ""))
    if channel == "whatsapp":
        return bool(
            getattr(settings, "DIC_WHATSAPP_ACCESS_TOKEN", "")
            and getattr(settings, "DIC_WHATSAPP_PHONE_NUMBER_ID", "")
            and getattr(settings, "DIC_WHATSAPP_OTP_TEMPLATE", "")
        )
    return False


def available_channels():
    return [
        RecoveryChannel("email", "Email", channel_available("email")),
        RecoveryChannel("sms", "SMS", channel_available("sms")),
        RecoveryChannel("whatsapp", "WhatsApp", channel_available("whatsapp")),
    ]


class EmailRecoveryAdapter:
    def send(self, destination, code):
        if not channel_available("email"):
            raise RecoveryDeliveryError("Email recovery is not configured.")
        sent = send_mail(
            subject="Your Dawana DIC registration recovery code",
            message=(
                f"Your one-time DIC registration recovery code is {code}. "
                "It expires in 10 minutes. If you did not request this code, "
                "you can ignore this message."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destination],
            fail_silently=False,
        )
        if sent != 1:
            raise RecoveryDeliveryError("Email provider did not accept the message.")


class ConfiguredSMSRecoveryAdapter:
    def send(self, destination, code):
        dotted_path = getattr(settings, "DIC_SMS_RECOVERY_ADAPTER", "")
        if not dotted_path:
            raise RecoveryDeliveryError("SMS recovery is not configured.")
        import_string(dotted_path)().send(destination, code)


class WhatsAppCloudRecoveryAdapter:
    def send(self, destination, code):
        _send_whatsapp_template(destination, code)


class DevelopmentTestRecoveryAdapter:
    def __init__(self, send_callable):
        self.send_callable = send_callable

    def send(self, destination, code):
        self.send_callable(destination, code)


def send_recovery_code(channel, destination, code):
    adapters = {
        "email": EmailRecoveryAdapter,
        "sms": ConfiguredSMSRecoveryAdapter,
        "whatsapp": WhatsAppCloudRecoveryAdapter,
    }
    adapter_class = adapters.get(channel)
    if not adapter_class:
        raise RecoveryDeliveryError("Unsupported recovery channel.")
    try:
        adapter_class().send(destination, code)
    except Exception as exc:
        logger.warning("DIC recovery delivery failed (channel=%s)", channel)
        if isinstance(exc, RecoveryDeliveryError):
            raise
        raise RecoveryDeliveryError("Recovery message delivery failed.") from exc


def _send_whatsapp_template(destination, code):
    if not channel_available("whatsapp"):
        raise RecoveryDeliveryError("WhatsApp recovery is not configured.")
    phone_number_id = settings.DIC_WHATSAPP_PHONE_NUMBER_ID
    version = settings.DIC_WHATSAPP_API_VERSION
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": re.sub(r"\D", "", destination),
        "type": "template",
        "template": {
            "name": settings.DIC_WHATSAPP_OTP_TEMPLATE,
            "language": {"code": settings.DIC_WHATSAPP_OTP_LANGUAGE},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": code}],
                }
            ],
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.DIC_WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.DIC_RECOVERY_PROVIDER_TIMEOUT_SECONDS,
        ) as response:
            result = json.loads(response.read(65536))
            if response.status >= 300 or not result.get("messages"):
                raise RecoveryDeliveryError(
                    "WhatsApp provider did not accept the message."
                )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RecoveryDeliveryError("WhatsApp delivery failed.") from exc


def whatsapp_support_url():
    digits = re.sub(r"\D", "", getattr(settings, "DIC_WHATSAPP_SUPPORT_NUMBER", ""))
    return f"https://wa.me/{digits}" if digits else None
