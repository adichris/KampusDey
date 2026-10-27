from apps.locations.importers import http, pipeline

from ._importcmd import ImportCommand


class Command(ImportCommand):
    help = "Import university/college points from OpenStreetMap (ODbL) and match them to campuses."

    def handle(self, *args, **opts):
        if opts.get("from_file"):
            data = http.load_json(opts["from_file"])
        elif opts.get("offline"):
            data = http.latest_raw("osm", "campuses") or {}
        else:
            data = pipeline.fetch_osm("campuses", pipeline.OSM_CAMPUS_QUERY)
        self.report(pipeline.import_osm_campuses(data))
