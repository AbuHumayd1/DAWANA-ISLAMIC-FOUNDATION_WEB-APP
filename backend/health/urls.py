from django.urls import path

from .views import HealthCheckView, WebHealthCheckView


urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("health/web/", WebHealthCheckView.as_view(), name="web-health"),
]
