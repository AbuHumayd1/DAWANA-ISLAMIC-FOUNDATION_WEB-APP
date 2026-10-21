import io
import json
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .payments import PaystackAPIError, PaystackClient, PaystackTransportError


@override_settings(
    PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_diagnostic_redaction_sentinel",
    PAYSTACK_CALLBACK_URL="https://example.test/callback", PAYSTACK_HTTP_TIMEOUT_SECONDS=10,
)
class PaystackDiagnosticTests(SimpleTestCase):
    sensitive = "private-reference customer@example.test https://checkout.paystack.com/private raw-provider-body Authorization"

    def initialize(self):
        return PaystackClient().initialize_transaction(
            email="customer@example.test", amount_kobo=100000,
            reference="private-reference", callback_url="https://example.test/callback",
            metadata={"private": self.sensitive},
        )

    def assert_safe_record(self, captured, status, classification):
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        data = json.loads(record.getMessage())
        self.assertEqual(set(data), {"event", "upstream_http_status", "failure_classification", "duration_ms"})
        self.assertEqual(data, {
            "event": "paystack_initialization_failure", "upstream_http_status": status,
            "failure_classification": classification, "duration_ms": 125,
        })
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        for secret in self.sensitive.split() + ["sk_test_diagnostic_redaction_sentinel"]:
            self.assertNotIn(secret, record.getMessage())

    @patch("dic.payments.urlopen")
    def test_http_rejections_keep_exact_status_without_logging_provider_body(self, mocked):
        cases = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 422: "unprocessable_entity", 429: "rate_limited", 409: "http_error", 500: "http_server_error", 502: "http_server_error"}
        for status, classification in cases.items():
            with self.subTest(status=status):
                body = io.BytesIO(self.sensitive.encode())
                mocked.side_effect = HTTPError("https://api.paystack.co/transaction/initialize", status, self.sensitive, {"Authorization": self.sensitive}, body)
                with patch("dic.payments.monotonic", side_effect=[10, 10.125]), self.assertLogs("dic.payments", level="WARNING") as captured:
                    with self.assertRaises(PaystackAPIError) as error:
                        self.initialize()
                self.assertEqual(error.exception.status_code, status)
                self.assertEqual(error.exception.definitive, 400 <= status < 500)
                self.assertTrue(body.closed)
                self.assert_safe_record(captured, status, classification)

    @patch("dic.payments.urlopen")
    def test_transport_and_timeout_do_not_log_exception_messages(self, mocked):
        for exception, classification in [(TimeoutError(self.sensitive), "timeout"), (URLError(TimeoutError(self.sensitive)), "timeout"), (URLError(self.sensitive), "transport_error"), (OSError(self.sensitive), "transport_error")]:
            with self.subTest(classification=classification):
                mocked.side_effect = exception
                with patch("dic.payments.monotonic", side_effect=[10, 10.125]), self.assertLogs("dic.payments", level="WARNING") as captured:
                    with self.assertRaises(PaystackTransportError):
                        self.initialize()
                self.assert_safe_record(captured, None, classification)

    @patch("dic.payments.urlopen")
    def test_invalid_responses_are_classified_without_logging_their_content(self, mocked):
        cases = [(self.sensitive.encode(), "invalid_json"), (b'[]', "invalid_response_shape"), (json.dumps({"status": False, "message": self.sensitive}).encode(), "rejected_response_envelope"), (b'x' * 1_048_577, "response_too_large")]
        for body, classification in cases:
            with self.subTest(classification=classification):
                response = mocked.return_value.__enter__.return_value
                response.getcode.return_value = 200
                response.read.return_value = body
                with patch("dic.payments.monotonic", side_effect=[10, 10.125]), self.assertLogs("dic.payments", level="WARNING") as captured:
                    with self.assertRaises(PaystackAPIError):
                        self.initialize()
                self.assert_safe_record(captured, 200, classification)

    @patch("dic.payments.urlopen")
    def test_success_and_verification_are_outside_failure_diagnostics(self, mocked):
        response = mocked.return_value.__enter__.return_value
        response.getcode.return_value = 200
        response.read.return_value = b'{"status":true,"data":{"reference":"private-reference"}}'
        with self.assertNoLogs("dic.payments", level="WARNING"):
            self.assertEqual(self.initialize(), {"reference": "private-reference"})
            mocked.side_effect = HTTPError("https://api.paystack.co/transaction/verify/private-reference", 401, self.sensitive, {}, io.BytesIO(b"private"))
            with self.assertRaises(PaystackAPIError):
                PaystackClient().verify_transaction("private-reference")
