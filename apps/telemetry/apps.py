from django.apps import AppConfig


class TelemetryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.telemetry"
    label = "telemetry"

    def ready(self):
        from . import signals  # noqa: F401
