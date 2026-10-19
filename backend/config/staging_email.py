"""Optional sandbox mail only; never deliver to operational participant contacts."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.smtp import EmailBackend


class SandboxEmailBackend(EmailBackend):
    def send_messages(self, email_messages):
        messages = list(email_messages or [])
        allowed = {value.lower() for value in settings.STAGING_EMAIL_RECIPIENTS}
        for message in messages:
            recipients = message.recipients()
            if (not settings.DIC_EMAIL_RECOVERY_ENABLED or not recipients
                    or any(value.lower() not in allowed or not value.lower().endswith('.test') for value in recipients)):
                raise ImproperlyConfigured('Staging message destination is not an approved sandbox recipient.')
        return super().send_messages(messages)
