"""Temporary staging gate; installed only by config.settings.staging."""
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


TESTER_GROUP = "DIC Staging Testers"


def is_staging_tester(user):
    return (
        user.is_authenticated and user.is_active
        and user.get_username() in getattr(settings, "STAGING_DIC_TESTER_USERNAMES", [])
        and (user.is_superuser or user.groups.filter(name=TESTER_GROUP).exists())
    )


class DICStagingTesterMiddleware:
    protected_views = {
        "order-create", "payment-initialize", "payment-verify", "pricing-accept",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if (
            not getattr(settings, "STAGING_DIC_TESTER_RESTRICTION_ENABLED", False)
            or request.method in ("GET", "HEAD", "OPTIONS", "TRACE")
            or not match
            or match.namespace != "dic"
            or match.url_name not in self.protected_views
        ):
            return None

        allowed = is_staging_tester(request.user)
        if not allowed:
            response = JsonResponse({
                "code": "staging_tester_required",
                "detail": (
                    "Staging tester access required. Sign in with an approved "
                    "tester account at /api/v1/dic/tester-access/login/, "
                    "then return to registration."
                ),
            }, status=403)
        else:
            # DRF's public bearer endpoints are csrf_exempt. The additional
            # staging session authority must still enforce CSRF explicitly.
            csrf = CsrfViewMiddleware(lambda request: None)
            rejection = csrf.process_view(request, lambda request: None, (), {})
            if rejection is None:
                return None
            response = JsonResponse({
                "code": "staging_tester_csrf_required",
                "detail": "Staging tester CSRF validation failed. Refresh and try again.",
            }, status=403)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
