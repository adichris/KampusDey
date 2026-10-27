from django.core.management.base import BaseCommand, CommandError

from apps.locations.geoip import update_geolite2


class Command(BaseCommand):
    help = "Download MaxMind GeoLite2 City with the account ID and licence key saved in the admin."

    def handle(self, *args, **opts):
        try:
            path = update_geolite2()
        except RuntimeError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"GeoLite2 database saved to {path}"))
