from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test event to Sentry and print its event id."

    def handle(self, *args, **options):
        if not settings.SENTRY_DSN:
            raise CommandError("SENTRY_DSN is not set.")
        import sentry_sdk

        event_id = sentry_sdk.capture_message(
            f"KampusDey Sentry check ({settings.SITE_ENVIRONMENT})", level="info"
        )
        sentry_sdk.flush(timeout=10)
        self.stdout.write(self.style.SUCCESS(f"Sent test event {event_id}."))
