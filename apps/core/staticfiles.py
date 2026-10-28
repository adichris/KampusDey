from django.contrib.staticfiles.apps import StaticFilesConfig


class KampusStaticFilesConfig(StaticFilesConfig):
    """collectstatic skips static/src (Tailwind sources); only the built CSS is published."""

    ignore_patterns = [*StaticFilesConfig.ignore_patterns, "src"]
