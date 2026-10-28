"""Schema-free Phase 3 policy. No identity inferred from payment or category."""
from django.conf import settings
from rest_framework.exceptions import ValidationError

DEFAULT_SESSION_SECONDS = 30 * 60


def session_seconds(remember=False):
    if type(remember) is not bool:
        raise ValidationError({'remember_device': 'Use true or false.'})
    if not remember:
        return DEFAULT_SESSION_SECONDS
    # Reuse the existing eight-hour application session ceiling, never rolling.
    return max(60, min(int(settings.SESSION_COOKIE_AGE), 8 * 60 * 60))


def capabilities():
    from .portal_accounts import enabled
    from .portal_google import google_available
    available = google_available()
    return {'session': {'default_seconds': DEFAULT_SESSION_SECONDS,
                'remember_seconds': session_seconds(True), 'sliding_refresh': False},
        'accounts': {'enabled': enabled()},
        'google': {'available': available,
            'message': 'Google sign-in is available for explicitly linked accounts.' if available else 'Google sign-in is not configured. Use your verified booking contact.'},
        'classes': {'available': True,
            'message': 'Approved academic classes appear after authorized staff assignment; setup may be pending.'}}


def class_assignment(registration_basis, participant_id=None, edition=None):
    if registration_basis == 'tutor':
        return {'status': 'not_applicable', 'name': None,
            'message': 'This is a tutor registration, not a camper class assignment.'}
    if participant_id is not None and edition is not None:
        from .launch_services import assigned_class
        return assigned_class(participant_id, edition)
    return {'status': 'pending_setup', 'name': None,
        'message': 'Your teaching class is not yet available. Registration category is not a class assignment.'}
