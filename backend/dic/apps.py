from django.apps import AppConfig


class DicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dic"
    verbose_name = "DIC configuration"

    def ready(self):
        from .portal_auth_logging import install
        install()
