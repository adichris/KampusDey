from pathlib import Path

from django.core.management.base import CommandError

from apps.locations.importers import http, pipeline

from ._importcmd import ImportCommand

HDX_DIR = http.RAW_DIR / "hdx"


def _latest(level: str):
    """Newest HDX file for admin level "1" or "2" (adm1/admin1 names; skips the _em variant)."""
    files = [
        f
        for pattern in (f"*adm{level}*", f"*admin{level}*")
        for f in HDX_DIR.glob(pattern)
        if f.suffix in (".geojson", ".json") and "_em" not in f.stem
    ]
    return sorted(set(files))[-1] if files else None


class Command(ImportCommand):
    help = "Load HDX COD-AB region (adm1) and district (adm2) polygons from data/raw/hdx/."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--districts", help="GeoJSON file with admin2 districts")

    def handle(self, *args, **opts):
        regions_path = opts.get("from_file") or _latest("1")
        if not regions_path:
            raise CommandError(
                "No admin1 GeoJSON found. Download COD-AB from "
                "https://data.humdata.org/m/dataset/cod-ab-gha into data/raw/hdx/ "
                "(file name containing 'adm1', optional 'adm2' file for districts)."
            )
        districts_path = opts.get("districts") or _latest("2")
        regions = http.load_json(regions_path)
        districts = (
            http.load_json(districts_path)
            if districts_path and Path(districts_path).exists()
            else None
        )
        self.report(pipeline.import_admin_boundaries(regions, districts))
