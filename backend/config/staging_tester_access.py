"""Temporary staging gate; installed only by config.settings.staging."""
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


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

        user = request.user
        allowed = (
            user.is_authenticated and user.is_active
            and user.get_username() in settings.STAGING_DIC_TESTER_USERNAMES
            and user.has_perm("dic.can_view_dic_operations")
        )
        if not allowed:
            response = JsonResponse({
                "code": "staging_tester_required",
                "detail": (
                    "Staging tester access required. Sign in with an approved "
                    "tester account at /dic/operations, then return to registration."
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
