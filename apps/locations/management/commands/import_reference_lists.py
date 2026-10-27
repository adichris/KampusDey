from django.core.management.base import BaseCommand

from apps.locations.importers import pipeline


class Command(BaseCommand):
    help = "Parse saved GTEC, Ministry of Health and Wikipedia lists in data/raw/ (no network)."

    def add_arguments(self, parser):
        parser.add_argument("--dir", help="Base directory (defaults to data/raw)")

    def handle(self, *args, **opts):
        summary = pipeline.import_reference_lists(opts.get("dir"))
        self.stdout.write(self.style.SUCCESS(summary.command))
        for line in summary.lines():
            self.stdout.write(f"  {line}")
