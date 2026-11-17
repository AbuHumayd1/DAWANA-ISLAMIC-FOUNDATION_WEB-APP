from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from dic.operations import operations_dashboard
from dic.production_inspection import production_inspection
from dic.production_population import production_population


urlpatterns = [
    path(
        "admin/dic/production-populate/",
        admin.site.admin_view(production_population),
        name="dic2026_production_population",
    ),
    path(
        "admin/dic/production-inspection/",
        admin.site.admin_view(production_inspection),
        name="dic2026_production_inspection",
    ),
    path(
        "admin/dic/operations/",
        admin.site.admin_view(operations_dashboard),
        name="dic_operations_dashboard",
    ),
    path("admin/", admin.site.urls),
    path("api/v1/dic/", include("dic.urls")),
    path("api/v1/foundation/", include("dic.foundation_urls")),
    path("api/v1/", include("health.urls")),
]

if getattr(settings, "STAGING_DIC_TESTER_ACCESS_AVAILABLE", False):
    from .staging_tester_views import TesterLoginView, TesterLogoutView

    urlpatterns += [
        path("api/v1/dic/tester-access/login/", TesterLoginView.as_view(), name="staging-tester-login"),
        path("api/v1/dic/tester-access/logout/", TesterLogoutView.as_view(), name="staging-tester-logout"),
    ]
