import hashlib
import hmac
import json
import logging
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings


PAYSTACK_API_BASE = "https://api.paystack.co"
logger = logging.getLogger("dic.payments")


def _http_failure_classification(status_code):
    return {
        400: "bad_request", 401: "unauthorized", 403: "forbidden",
        422: "unprocessable_entity", 429: "rate_limited",
    }.get(status_code, "http_server_error" if status_code >= 500 else "http_error")


class PaystackConfigurationError(Exception):
    pass


class PaystackTransportError(Exception):
    pass


class PaystackAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def definitive(self):
        return self.status_code is not None and 400 <= self.status_code < 500


def paystack_secret_key():
    key = settings.PAYSTACK_SECRET_KEY
    if settings.PAYSTACK_MODE != "test":
        raise PaystackConfigurationError("Paystack test mode is required.")
    if not key:
        raise PaystackConfigurationError("Paystack credentials are not configured.")
    if not key.startswith("sk_test_"):
        raise PaystackConfigurationError(
            "Only a Paystack test-mode secret key is allowed."
        )
    callback_url = settings.PAYSTACK_CALLBACK_URL
    if callback_url:
        try:
            parsed = urlparse(callback_url)
            port = parsed.port
        except ValueError:
            raise PaystackConfigurationError(
                "PAYSTACK_CALLBACK_URL must be an absolute HTTPS URL."
            ) from None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or port not in (None, 443)
        ):
            raise PaystackConfigurationError(
                "PAYSTACK_CALLBACK_URL must be an absolute HTTPS URL."
            )
    if not 1 <= settings.PAYSTACK_HTTP_TIMEOUT_SECONDS <= 30:
        raise PaystackConfigurationError(
            "PAYSTACK_HTTP_TIMEOUT_SECONDS must be between 1 and 30."
        )
    return key


def verify_webhook_signature(raw_body, signature, secret_key):
    if not signature:
        return False
    expected = hmac.new(
        secret_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class PaystackClient:
    def __init__(self):
        self.secret_key = paystack_secret_key()
        self.timeout = settings.PAYSTACK_HTTP_TIMEOUT_SECONDS

    def _request(self, method, path, payload=None):
        started = monotonic()
        upstream_status = None

        def diagnose(classification):
            # Only constants, a validated status and elapsed time cross this
            # boundary. Never serialize requests, exceptions or provider data.
            if method == "POST" and path == "/transaction/initialize":
                logger.warning(json.dumps({
                    "event": "paystack_initialization_failure",
                    "upstream_http_status": upstream_status,
                    "failure_classification": classification,
                    "duration_ms": round(max(0, monotonic() - started) * 1000),
                }, separators=(",", ":")))

        body = None
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{PAYSTACK_API_BASE}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                code = response.getcode()
                if type(code) is int and 100 <= code <= 599:
                    upstream_status = code
                response_body = response.read(1_048_577)
                if len(response_body) > 1_048_576:
                    diagnose("response_too_large")
                    raise PaystackAPIError("Provider response exceeded the size limit.")
                response_data = json.loads(response_body)
        except HTTPError as exc:
            if type(exc.code) is int and 100 <= exc.code <= 599:
                upstream_status = exc.code
            exc.close()
            diagnose(_http_failure_classification(upstream_status) if upstream_status is not None else "http_error")
            raise PaystackAPIError(
                "Payment provider returned an HTTP error.",
                status_code=exc.code,
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            diagnose("timeout" if isinstance(reason, TimeoutError) else "transport_error")
            raise PaystackTransportError(
                "Payment provider could not be reached."
            ) from None
        except (ValueError, UnicodeDecodeError, RecursionError):
            diagnose("invalid_json")
            raise PaystackAPIError("Payment provider returned invalid JSON.") from None

        if not isinstance(response_data, dict):
            diagnose("invalid_response_shape")
            raise PaystackAPIError("Payment provider returned an invalid response.")
        if method == "POST" and path == "/transaction/initialize" and (
            response_data.get("status") is not True
            or not isinstance(response_data.get("data"), dict)
        ):
            diagnose("rejected_response_envelope")
        return response_data

    def initialize_transaction(
        self,
        *,
        email,
        amount_kobo,
        reference,
        callback_url="",
        metadata=None,
    ):
        payload = {
            "email": email,
            "amount": amount_kobo,
            "currency": "NGN",
            "reference": reference,
            "metadata": metadata or {},
        }
        if callback_url:
            payload["callback_url"] = callback_url

        response = self._request(
            "POST",
            "/transaction/initialize",
            payload,
        )
        if response.get("status") is not True or not isinstance(
            response.get("data"),
            dict,
        ):
            raise PaystackAPIError("Payment provider rejected initialization.")
        return response["data"]

    def verify_transaction(self, reference):
        response = self._request(
            "GET",
            f"/transaction/verify/{quote(reference, safe='')}",
        )
        if response.get("status") is not True or not isinstance(
            response.get("data"),
            dict,
        ):
            raise PaystackAPIError("Payment provider could not verify the transaction.")
        return response["data"]
