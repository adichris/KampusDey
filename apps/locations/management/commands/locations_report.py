import json

from django.core.management.base import BaseCommand

from apps.locations.importers import pipeline


class Command(BaseCommand):
    help = "Counts per source, match rates, campuses without points, duplicates, GTEC flags."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        report = pipeline.locations_report()
        if opts["json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
            return
        for key, value in report.items():
            if isinstance(value, list | dict) and len(value) > 8:
                self.stdout.write(f"{key}: {len(value)} items")
                items = list(value.items()) if isinstance(value, dict) else value
                for item in items[:8]:
                    self.stdout.write(f"    {item}")
            else:
                self.stdout.write(f"{key}: {value}")
