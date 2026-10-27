from django.core.management.base import BaseCommand

from apps.external.models import ExternalSource
from apps.external.services import SourceNotRunnable, run_source


class Command(BaseCommand):
    help = "Run every approved + enabled external source once (make import-external). Needs internet."

    def add_arguments(self, parser):
        parser.add_argument("--source", help="Only this source slug")

    def handle(self, *args, **opts):
        qs = ExternalSource.objects.all()
        if opts.get("source"):
            qs = qs.filter(slug=opts["source"])
        for source in qs:
            try:
                run = run_source(source)
            except SourceNotRunnable as exc:
                self.stdout.write(f"{source.slug}: skipped ({exc})")
                continue
            self.stdout.write(
                f"{source.slug}: {run.status} created={run.created} updated={run.updated} removed={run.removed}"
                + (f" error={run.error}" if run.error else "")
            )
