from django.apps import AppConfig


class LocationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.locations"
    label = "locations"

    def ready(self):
        from . import signals  # noqa: F401
