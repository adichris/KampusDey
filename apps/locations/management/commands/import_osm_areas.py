from apps.locations.importers import http, pipeline

from ._importcmd import ImportCommand


class Command(ImportCommand):
    help = "Import neighbourhoods near each campus with a point from OpenStreetMap (2 s between calls)."

    def handle(self, *args, **opts):
        fetcher = None
        if opts.get("from_file"):
            data = http.load_json(opts["from_file"])

            def fetcher(campus):
                return data
        elif opts.get("offline"):

            def fetcher(campus):
                return http.latest_raw("osm", f"areas-{campus.slug}") or {"elements": []}

        self.report(pipeline.import_osm_areas(fetcher))
