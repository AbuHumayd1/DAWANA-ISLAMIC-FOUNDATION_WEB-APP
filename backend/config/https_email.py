"""Minimal Django email backend for Resend HTTPS; no SDK or provider payload logs."""
import json
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.exceptions import ImproperlyConfigured


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the API credential to a redirect destination.


class EmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not getattr(settings, 'RESEND_API_KEY', ''):
            raise ImproperlyConfigured('Configure the HTTPS email API credential.')
        sent = 0
        for message in email_messages:
            try:
                if message.attachments or message.bcc or message.cc or message.extra_headers:
                    raise ValueError('This transactional backend supports plain text and explicit recipients only.')
                payload = dict(sender=message.from_email, to=message.to, subject=message.subject, text=message.body)
                payload['from'] = payload.pop('sender')
                if message.reply_to:
                    payload['reply_to'] = message.reply_to
                request = Request('https://api.resend.com/emails',
                    data=json.dumps(payload).encode('utf-8'), method='POST',
                    headers={'Authorization': 'Bearer ' + settings.RESEND_API_KEY,
                             'Content-Type': 'application/json', 'User-Agent': 'DawanaDIC/1.0'})
                # Standard HTTPSHandler validates the server certificate/hostname.
                with build_opener(HTTPSHandler(), NoRedirect()).open(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    result = json.loads(response.read(65536))
                    if response.status != 200 or not isinstance(result, dict) or not result.get('id'):
                        raise ValueError('Email provider did not accept the message.')
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise RuntimeError('Transactional email delivery is temporarily unavailable.') from None
        return sent
