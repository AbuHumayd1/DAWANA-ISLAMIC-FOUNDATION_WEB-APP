from django.urls import re_path
from .urls import urlpatterns as application_urls
from .spa import frontend

# Backend namespaces must never fall through to the SPA.
urlpatterns = [*application_urls, re_path(
    r'^(?!(?:api|admin|static|media|health|_container)(?:/|$))(?P<path>.*)$', frontend)]
