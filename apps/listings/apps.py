from django.apps import AppConfig


class ListingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.listings"
    label = "listings"

    def ready(self):
        from . import signals  # noqa: F401
