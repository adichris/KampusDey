from apps.locations.importers import http, pipeline

from ._importcmd import ImportCommand


class Command(ImportCommand):
    help = "Import higher-education institutions in Ghana from Wikidata (CC0)."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--campuses-file", help="Saved JSON for the sub-campus query")

    def handle(self, *args, **opts):
        if opts.get("from_file"):
            data = http.load_json(opts["from_file"])
            campuses = http.load_json(opts["campuses_file"]) if opts.get("campuses_file") else None
        elif opts.get("offline"):
            data = http.latest_raw("wikidata", "institutions") or {}
            campuses = http.latest_raw("wikidata", "campuses")
        else:
            data, campuses = pipeline.fetch_wikidata()
        self.report(pipeline.import_wikidata_institutions(data, campuses))
