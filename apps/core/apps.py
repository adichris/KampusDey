from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        from auditlog.registry import auditlog
        from django.apps import apps

        get = apps.get_model
        auditlog.register(
            get("listings", "Listing"),
            exclude_fields=[
                "search_vector",
                "score",
                "views_7d",
                "taps_7d",
                "likes_7d",
                "updated_at",
            ],
        )
        auditlog.register(get("accounts", "Profile"))
        auditlog.register(get("accounts", "VerificationRequest"), exclude_fields=["document"])
        # Secrets are excluded so the audit log never stores them.
        from apps.sitesettings.models import secret_field_names

        auditlog.register(
            get("sitesettings", "IntegrationSettings"), exclude_fields=secret_field_names()
        )
        auditlog.register(get("boosts", "Boost"))
        auditlog.register(get("engagement", "Report"))
