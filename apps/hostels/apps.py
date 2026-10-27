from django.apps import AppConfig


class HostelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hostels"
    label = "hostels"

    def ready(self):
        from . import signals  # noqa: F401
