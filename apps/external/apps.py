from django.apps import AppConfig


class ExternalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.external"
    label = "external"

    def ready(self):
        from . import signals  # noqa: F401
