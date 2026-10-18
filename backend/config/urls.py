from django.contrib import admin
from django.urls import include, path

from dic.operations import operations_dashboard


urlpatterns = [
    path(
        "admin/dic/operations/",
        admin.site.admin_view(operations_dashboard),
        name="dic_operations_dashboard",
    ),
    path("admin/", admin.site.urls),
    path("api/v1/dic/", include("dic.urls")),
    path("api/v1/", include("health.urls")),
]
