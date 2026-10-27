from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the whole location import in order (make import-locations). Needs internet."

    def add_arguments(self, parser):
        parser.add_argument("--offline", action="store_true", help="Use cached raw responses only")
        parser.add_argument("--skip-boundaries", action="store_true")
        parser.add_argument("--skip-areas", action="store_true")

    def handle(self, *args, **opts):
        offline = {"offline": True} if opts["offline"] else {}
        call_command("seed_locations")
        if not opts["skip_boundaries"]:
            try:
                call_command("import_admin_boundaries")
            except Exception as exc:  # missing download → continue; the report shows it
                self.stderr.write(f"import_admin_boundaries skipped: {exc}")
        call_command("import_osm_towns", **offline)
        call_command("import_wikidata_institutions", **offline)
        call_command("import_osm_campuses", **offline)
        call_command("import_reference_lists")
        if not opts["skip_areas"]:
            call_command("import_osm_areas", **offline)
        call_command("locations_report")
