import hashlib
import hmac
import json
import logging
from http.client import HTTPException
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings


PAYSTACK_API_BASE = "https://api.paystack.co"
PAYSTACK_USER_AGENT = "DawanaDIC/1.0"
logger = logging.getLogger("dic.payments")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _initialization_rejection_diagnostic(response):
    """Recognize a response, never export its body, message, URL or headers.

    TLS/endpoint plus schema are conservative recognition gates, not proof of
    application origin behind an edge proxy. Unknown codes stay unknown.
    """
    result = {
        "rejection_response_kind": "unrecognized_response",
        "provider_error_category": "unknown_provider_rejection",
    }
    try:
        if response.geturl() != f"{PAYSTACK_API_BASE}/transaction/initialize":
            result["rejection_response_kind"] = "unexpected_response_origin"
            return result
        headers = response.headers or {}
        if headers.get("cf-mitigated", "").strip().lower() == "challenge":
            result["rejection_response_kind"] = "edge_challenge"
            return result
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type == "text/html":
            result["rejection_response_kind"] = "html_response"
            return result
        if content_type != "application/json":
            result["rejection_response_kind"] = "non_json_response"
            return result
        body = response.read(8193)
        if len(body) > 8192:
            result["rejection_response_kind"] = "oversized_error_response"
            return result
        if body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            result["rejection_response_kind"] = "html_response"
            return result
        data = json.loads(body, object_pairs_hook=_unique_json_object)
        result["rejection_response_kind"] = "unrecognized_json"
        if not (
            isinstance(data, dict) and data.get("status") is False
            and isinstance(data.get("type"), str)
            and data["type"] in ("api_error", "validation_error", "processor_error")
            and isinstance(data.get("code"), str)
            and isinstance(data.get("message"), str)
        ):
            return result
        result["rejection_response_kind"] = "paystack_json_error"
        # Documented type/code pairs only; no substring matching or message
        # interpolation. Extend only after reviewing Paystack documentation.
        categories = {
            ("validation_error", "missing_params"): "missing_parameters",
            ("api_error", "rate_limited"): "rate_limited",
        }
        result["provider_error_category"] = categories.get(
            (data["type"], data["code"]), "unknown_provider_rejection"
        )
    except (OSError, ValueError, RecursionError, HTTPException):
        # Diagnostic read/decode failure must never replace the original HTTP
        # error or alter its definitive/unknown payment-state handling.
        result["rejection_response_kind"] = "unreadable_error_response"
    return result


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

        def diagnose(classification, rejection=None):
            # Only constants, a validated status and elapsed time cross this
            # boundary. Never serialize requests, exceptions or provider data.
            if method == "POST" and path == "/transaction/initialize":
                diagnostic = {
                    "event": "paystack_initialization_failure",
                    "upstream_http_status": upstream_status,
                    "failure_classification": classification,
                    "duration_ms": round(max(0, monotonic() - started) * 1000),
                }
                if rejection is not None:
                    diagnostic.update(rejection)
                logger.warning(json.dumps(diagnostic, separators=(",", ":")))

        body = None
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
            "User-Agent": PAYSTACK_USER_AGENT,
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
            try:
                rejection = (
                    _initialization_rejection_diagnostic(exc)
                    if method == "POST" and path == "/transaction/initialize"
                    else None
                )
            finally:
                exc.close()
            diagnose(_http_failure_classification(upstream_status) if upstream_status is not None else "http_error", rejection)
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
