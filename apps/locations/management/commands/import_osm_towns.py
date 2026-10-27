from apps.locations.importers import http, pipeline

from ._importcmd import ImportCommand


class Command(ImportCommand):
    help = "Import cities and towns from OpenStreetMap; assign regions by point-in-polygon."

    def handle(self, *args, **opts):
        if opts.get("from_file"):
            data = http.load_json(opts["from_file"])
        elif opts.get("offline"):
            data = http.latest_raw("osm", "towns") or {}
        else:
            data = pipeline.fetch_osm("towns", pipeline.OSM_TOWN_QUERY)
        self.report(pipeline.import_osm_towns(data))
