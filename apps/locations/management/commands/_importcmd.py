"""Shared base for import commands: --from-file uses saved/recorded responses (no network)."""

from django.core.management.base import BaseCommand


class ImportCommand(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--from-file", dest="from_file", help="Use a saved JSON response")
        parser.add_argument("--offline", action="store_true", help="Use the latest cached raw response")

    def report(self, summary):
        self.stdout.write(self.style.SUCCESS(f"{summary.command} ({summary.source})"))
        for line in summary.lines():
            self.stdout.write(f"  {line}")
