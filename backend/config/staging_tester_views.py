"""Ordinary tester login without access to the operations portal or Admin."""
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.http import HttpResponse
from rest_framework.throttling import ScopedRateThrottle

from .staging_tester_access import is_staging_tester


class TesterAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_staging_tester(user):
            raise self.get_invalid_login_error()


class TesterLoginView(LoginView):
    authentication_form = TesterAuthenticationForm
    template_name = "dic/staging_tester_login.html"
    next_page = "/dic/register"
    throttle_scope = "dic_staging_tester_login"

    def post(self, request, *args, **kwargs):
        throttle = ScopedRateThrottle()
        throttle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        if not throttle.allow_request(request, self):
            response = HttpResponse("Too many login attempts. Try again later.", status=429)
            response["Retry-After"] = str(max(1, int(throttle.wait() or 1)))
            response["Cache-Control"] = "no-store"
            return response
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "title": "DIC staging tester access",
            "tester_authorized": is_staging_tester(self.request.user),
        }


class TesterLogoutView(LogoutView):
    next_page = "/api/v1/dic/tester-access/login/"
