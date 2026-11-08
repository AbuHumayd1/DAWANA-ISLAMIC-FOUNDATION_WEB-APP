"""No real provider calls. Verify HTTPS request, error redaction and delivery result."""
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings
from django.core.mail import EmailMessage
from .https_email import EmailBackend, NoRedirect


@override_settings(RESEND_API_KEY='re_synthetic', EMAIL_TIMEOUT=8)
class HttpsEmailTests(SimpleTestCase):
    def test_transactional_email_uses_fixed_https_endpoint_and_bounded_timeout(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'{"id":"synthetic-message"}'
        with patch('config.https_email.build_opener', return_value=opener):
            sent = EmailBackend().send_messages([EmailMessage('Verify', 'One-time link', 'sender@example.test', ['owner@example.test'])])
        self.assertEqual(sent, 1)
        self.assertEqual(opener.open.call_args.args[0].full_url, 'https://api.resend.com/emails')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 8)

    def test_failure_does_not_expose_api_key_or_provider_payload_and_redirect_is_rejected(self):
        with patch('config.https_email.build_opener') as factory:
            factory.return_value.open.side_effect = RuntimeError('re_synthetic private payload')
            with self.assertRaisesRegex(RuntimeError, '^Transactional email delivery is temporarily unavailable.$'):
                EmailBackend().send_messages([EmailMessage('Verify', 'private code', 'sender@example.test', ['owner@example.test'])])
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))
