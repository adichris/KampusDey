"""Location importers (DATA_SOURCES_PROMPT §6). Each function is idempotent.

Every importer accepts already-parsed data so tests run against recorded responses in
`tests/fixtures/sources/`; with `data=None` it fetches from the network and caches the raw
response under `data/raw/<source>/`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from html.parser import HTMLParser
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core import geo
from apps.core.text import normalise_name, trigram_similarity

from ..classify import classify_kind
from ..models import (
    Area,
    Campus,
    District,
    GtecStatus,
    Institution,
    Region,
    ReviewStatus,
    Source,
    Town,
)
from . import http
from .base import (
    Summary,
    apply_fields,
    find_town_by_name,
    link_record,
    match_campus,
    match_institution,
    nearest_town,
    provenance,
    save_if_changed,
    stage,
)

logger = logging.getLogger(__name__)

WIKIDATA_QUERY = """
SELECT ?item ?itemLabel (SAMPLE(?short) AS ?shortName) (SAMPLE(?coord) AS ?coords)
       (SAMPLE(?admLabel) AS ?adm) (SAMPLE(?website) AS ?site)
       (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types)
       (SAMPLE(?dissolved) AS ?diss) WHERE {
  ?item wdt:P17 wd:Q117 .
  ?item wdt:P31/wdt:P279* wd:Q38723 .
  OPTIONAL { ?item wdt:P1813 ?short . FILTER(LANG(?short) = "en") }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P131 ?admE . ?admE rdfs:label ?admLabel . FILTER(LANG(?admLabel) = "en") }
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P31 ?type . ?type rdfs:label ?typeLabel . FILTER(LANG(?typeLabel) = "en") }
  OPTIONAL { ?item wdt:P576 ?dissolved }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
GROUP BY ?item ?itemLabel
"""

WIKIDATA_CAMPUS_QUERY = """
SELECT ?item ?itemLabel ?parent (SAMPLE(?coord) AS ?coords) (SAMPLE(?admLabel) AS ?adm) WHERE {
  VALUES ?parent { %s }
  { ?item wdt:P749 ?parent } UNION { ?item wdt:P361 ?parent }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P131 ?admE . ?admE rdfs:label ?admLabel . FILTER(LANG(?admLabel) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
GROUP BY ?item ?itemLabel ?parent
"""

OSM_CAMPUS_QUERY = """[out:json][timeout:180];
area["ISO3166-1"="GH"][admin_level=2]->.gh;
nwr["amenity"~"^(university|college)$"]["name"](area.gh);
out center tags;"""

OSM_TOWN_QUERY = """[out:json][timeout:180];
area["ISO3166-1"="GH"][admin_level=2]->.gh;
node["place"~"^(city|town)$"](area.gh);
out tags;"""

OSM_AREA_QUERY = """[out:json][timeout:60];
node["place"~"^(suburb|neighbourhood|quarter|village|hamlet)$"]["name"](around:{radius},{lat},{lon});
out tags;"""


def unique_slug(model, value: str) -> str:
    base = slugify(value)[:150] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _value(row, key):
    cell = row.get(key)
    return cell.get("value") if isinstance(cell, dict) else cell


def region_for_point(lat, lng):
    from ..services import region_for_point as rfp

    return rfp(lat, lng)


# ---------------------------------------------------------------------------
# HDX admin boundaries
# ---------------------------------------------------------------------------
def _region_key(name: str) -> str:
    return normalise_name(re.sub(r"\bregion\b", "", name or "", flags=re.I))


@transaction.atomic
def import_admin_boundaries(
    regions_geojson: dict, districts_geojson: dict | None = None
) -> Summary:
    summary = Summary("import_admin_boundaries", Source.HDX)
    regions = {_region_key(r.name): r for r in Region.objects.all()}
    by_pcode = {}
    for feature in regions_geojson.get("features", []):
        props = feature.get("properties", {})
        name = props.get("ADM1_EN") or props.get("admin1Name_en") or props.get("name")
        pcode = props.get("ADM1_PCODE") or props.get("admin1Pcode") or ""
        region = regions.get(_region_key(name))
        if region is None:
            summary.inc("regions_unmatched")
            continue
        boundary = geo.to_multipolygon(feature.get("geometry"))
        box = geo.geometry_bbox(boundary)
        values = {
            "hdx_pcode": pcode,
            "boundary": boundary,
            **(
                {"min_lat": box[0], "max_lat": box[1], "min_lng": box[2], "max_lng": box[3]}
                if box
                else {}
            ),
            **provenance(Source.HDX, pcode, "https://data.humdata.org/dataset/cod-ab-gha"),
        }
        # Regions keep the seeded name; HDX adds geometry and the P-code.
        changed = apply_fields(region, values)
        if save_if_changed(region, changed):
            summary.inc("regions_updated")
        else:
            summary.inc("regions_unchanged")
        by_pcode[pcode] = region
    for feature in (districts_geojson or {}).get("features", []):
        props = feature.get("properties", {})
        name = props.get("ADM2_EN") or props.get("name")
        pcode = props.get("ADM2_PCODE") or ""
        region = by_pcode.get(props.get("ADM1_PCODE"))
        if not (name and pcode and region):
            summary.inc("districts_skipped")
            continue
        district = District.objects.filter(hdx_pcode=pcode).first() or District(
            region=region, name=name, slug=unique_slug(District, f"{name}-{region.slug}")
        )
        boundary = geo.to_multipolygon(feature.get("geometry"))
        box = geo.geometry_bbox(boundary)
        changed = apply_fields(
            district,
            {
                "name": name,
                "hdx_pcode": pcode,
                "boundary": boundary,
                **(
                    {"min_lat": box[0], "max_lat": box[1], "min_lng": box[2], "max_lng": box[3]}
                    if box
                    else {}
                ),
                **provenance(Source.HDX, pcode, "https://data.humdata.org/dataset/cod-ab-gha"),
            },
        )
        created = district.pk is None
        if save_if_changed(district, changed):
            summary.inc("districts_created" if created else "districts_updated")
    return summary.log()


def district_for_point(lat, lng):
    for d in District.objects.filter(
        min_lat__lte=lat, max_lat__gte=lat, min_lng__lte=lng, max_lng__gte=lng
    ):
        if geo.geometry_contains(d.boundary, lat, lng):
            return d
    return None


# ---------------------------------------------------------------------------
# OSM towns
# ---------------------------------------------------------------------------
@transaction.atomic
def import_osm_towns(data: dict) -> Summary:
    summary = Summary("import_osm_towns", Source.OSM)
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        lat, lng = el.get("lat"), el.get("lon")
        if not name or lat is None:
            summary.inc("skipped_no_name_or_point")
            continue
        source_id = f"node/{el['id']}"
        record = stage(Source.OSM, "town", source_id, el)
        region = region_for_point(lat, lng)
        if region is None:
            summary.inc("skipped_no_region")
            continue
        town = (
            Town.objects.filter(source=Source.OSM, source_id=source_id).first()
            or find_town_by_name(name, region)
            or Town(region=region, name=name, slug=unique_slug(Town, f"{name}-{region.slug}"))
        )
        created = town.pk is None
        values = {
            "name": name if created else None,
            "region": region,
            "district": district_for_point(lat, lng),
            "lat": lat,
            "lng": lng,
        }
        if created or not town.source_id or town.source == Source.OSM:
            values.update(
                provenance(Source.OSM, source_id, f"https://www.openstreetmap.org/{source_id}")
            )
        changed = apply_fields(town, values)
        if save_if_changed(town, changed):
            summary.inc("towns_created" if created else "towns_updated")
        else:
            summary.inc("towns_unchanged")
        link_record(record, town, "osm_id" if not created else "new", 1.0)
    return summary.log()


# ---------------------------------------------------------------------------
# Wikidata institutions
# ---------------------------------------------------------------------------
def _resolve_town(point, adm_label, region):
    if point:
        town = nearest_town(point[0], point[1])
        if town:
            return town
    town = find_town_by_name(adm_label, region)
    if town:
        return town
    if adm_label and region is not None:
        return Town.objects.create(
            region=region,
            name=re.sub(
                r" (Municipal|Metropolitan)?\s*(District|Municipality|Assembly)$", "", adm_label
            ),
            slug=unique_slug(Town, f"{adm_label}-{region.slug}"),
            source=Source.WIKIDATA,
            confidence=0.5,
            licence="CC0 1.0",
            retrieved_at=timezone.now(),
        )
    return None


def _ensure_main_campus(
    inst: Institution, point, town, source, source_id, url, confidence, summary
):
    campus = inst.campuses.order_by("pk").first()
    if campus is None:
        existing = match_campus(inst.name, point, town.region if town else None)
        if existing.obj is not None and existing.obj.institution_id in (None, inst.pk):
            campus = existing.obj
            if campus.institution_id is None and not campus.is_field_locked("institution"):
                campus.institution = inst
                campus.save(update_fields=["institution", "updated_at"])
    if campus is None:
        if town is None:
            summary.inc("campus_skipped_no_town")
            return None
        campus = Campus(
            institution=inst,
            town=town,
            name=inst.name,
            short_name=inst.short_name,
            kind=inst.kind,
            slug=unique_slug(
                Campus, inst.short_name and f"{inst.short_name}-{town.name}" or inst.name
            ),
        )
        apply_fields(
            campus,
            {
                "lat": point[0] if point else None,
                "lng": point[1] if point else None,
                **provenance(source, source_id, url, confidence),
            },
        )
        save_if_changed(campus, [])
        summary.inc("campuses_created")
        return campus
    values = {"short_name": inst.short_name or None}
    if point and (
        not campus.has_point or campus.source in (Source.WIKIDATA, Source.MANUAL, Source.OSM)
    ):
        values.update(lat=point[0], lng=point[1])
    if campus.source == Source.MANUAL and not campus.source_id:
        values.update(provenance(source, source_id, url, confidence))
    if town and campus.town_id != town.pk and campus.source != Source.MANUAL:
        values["town"] = town
    changed = apply_fields(campus, values)
    if save_if_changed(campus, changed):
        summary.inc("campuses_updated")
    return campus


@transaction.atomic
def import_wikidata_institutions(data: dict, campus_data: dict | None = None) -> Summary:
    summary = Summary("import_wikidata_institutions", Source.WIKIDATA)
    rows = data.get("results", {}).get("bindings", [])
    for row in rows:
        uri = _value(row, "item") or ""
        qid = uri.rsplit("/", 1)[-1]
        name = _value(row, "itemLabel")
        if not qid or not name or name == qid:
            summary.inc("skipped_no_label")
            continue
        record = stage(Source.WIKIDATA, "institution", qid, row)
        if _value(row, "diss"):
            summary.inc("skipped_dissolved")
            continue
        point = geo.parse_wkt_point(_value(row, "coords"))
        region = region_for_point(*point) if point else None
        match = match_institution(name, qid, region, point)
        inst = match.obj or Institution(name=name, slug=unique_slug(Institution, name))
        created = inst.pk is None
        url = f"https://www.wikidata.org/wiki/{qid}"
        confidence = (
            1.0 if match.method == "wikidata_id" else (match.confidence if not created else 0.5)
        )
        values = {
            "name": name if created else None,
            "short_name": _value(row, "shortName"),
            "website": _value(row, "site"),
            "wikidata_id": qid
            if not Institution.objects.filter(wikidata_id=qid).exclude(pk=inst.pk).exists()
            else None,
        }
        if created:
            values["kind"] = classify_kind(name)
        if created or inst.source in (Source.WIKIDATA, Source.MANUAL, Source.WIKIPEDIA):
            values.update(provenance(Source.WIKIDATA, qid, url, confidence))
            if not created and inst.source == Source.WIKIDATA:
                values.pop("confidence")  # keep the confidence from the original match
        changed = apply_fields(inst, values)
        if save_if_changed(inst, changed):
            summary.inc("institutions_created" if created else "institutions_updated")
        else:
            summary.inc("institutions_unchanged")
        link_record(record, inst, match.method, confidence)
        town = _resolve_town(point, _value(row, "adm"), region)
        _ensure_main_campus(inst, point, town, Source.WIKIDATA, qid, url, confidence, summary)
        if point:
            summary.inc("with_coordinates")
    for row in (campus_data or {}).get("results", {}).get("bindings", []):
        qid = (_value(row, "item") or "").rsplit("/", 1)[-1]
        parent_qid = (_value(row, "parent") or "").rsplit("/", 1)[-1]
        name = _value(row, "itemLabel")
        parent = Institution.objects.filter(wikidata_id=parent_qid).first()
        if not (qid and name and parent):
            continue
        record = stage(Source.WIKIDATA, "campus", qid, row)
        point = geo.parse_wkt_point(_value(row, "coords"))
        region = region_for_point(*point) if point else None
        campus = Campus.objects.filter(source=Source.WIKIDATA, source_id=qid).first()
        town = _resolve_town(point, _value(row, "adm"), region)
        if campus is None:
            if town is None:
                summary.inc("campus_skipped_no_town")
                continue
            campus = Campus(
                institution=parent,
                town=town,
                name=name,
                kind=parent.kind,
                slug=unique_slug(Campus, name),
            )
        created = campus.pk is None
        changed = apply_fields(
            campus,
            {
                "lat": point[0] if point else None,
                "lng": point[1] if point else None,
                **provenance(Source.WIKIDATA, qid, f"https://www.wikidata.org/wiki/{qid}", 0.9),
            },
        )
        if save_if_changed(campus, changed):
            summary.inc("sub_campuses_created" if created else "sub_campuses_updated")
        link_record(record, campus, "parent", 0.9)
    return summary.log()


# ---------------------------------------------------------------------------
# OSM campuses
# ---------------------------------------------------------------------------
def _el_point(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    center = el.get("center")
    return (center["lat"], center["lon"]) if center else None


@transaction.atomic
def import_osm_campuses(data: dict) -> Summary:
    summary = Summary("import_osm_campuses", Source.OSM)
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        point = _el_point(el)
        if not name:
            continue
        source_id = f"{el['type']}/{el['id']}"
        record = stage(Source.OSM, "campus", source_id, el)
        url = f"https://www.openstreetmap.org/{source_id}"
        campus = Campus.objects.filter(osm_id=source_id).first()
        method, confidence = "osm_id", 1.0
        if campus is None and tags.get("wikidata"):
            inst = Institution.objects.filter(wikidata_id=tags["wikidata"]).first()
            campus = inst.campuses.order_by("pk").first() if inst else None
            method = "wikidata_tag"
        if campus is None:
            region = region_for_point(*point) if point else None
            match = match_campus(name, point, region)
            campus, method, confidence = match.obj, match.method, match.confidence
        if campus is None:
            region = region_for_point(*point) if point else None
            town = nearest_town(*point) if point else None
            if town is None:
                summary.inc("skipped_no_town")
                continue
            inst_match = match_institution(name, tags.get("wikidata"), region, point)
            inst = inst_match.obj
            if inst is None:
                inst = Institution.objects.create(
                    name=name,
                    slug=unique_slug(Institution, name),
                    kind=classify_kind(name),
                    short_name=tags.get("short_name", ""),
                    website=tags.get("website", "")[:200],
                    **provenance(Source.OSM, source_id, url, 0.5),
                    retrieved_at=timezone.now(),
                )
                summary.inc("institutions_created")
            campus = Campus(
                institution=inst,
                town=town,
                name=name,
                kind=inst.kind,
                osm_id=source_id,
                slug=unique_slug(Campus, name),
                lat=point[0],
                lng=point[1],
                **provenance(Source.OSM, source_id, url, 0.5),
            )
            save_if_changed(campus, [])
            summary.inc("campuses_created")
            link_record(record, campus, "new", 0.5)
            continue
        values = {"osm_id": source_id}
        # Prefer Wikidata coordinates (CC0) — OSM only fills missing points.
        if point and not campus.has_point:
            values.update(lat=point[0], lng=point[1])
            summary.inc("points_filled")
        changed = apply_fields(campus, values)
        if save_if_changed(campus, changed, retrieved=False):
            summary.inc("campuses_updated")
        else:
            summary.inc("campuses_unchanged")
        link_record(record, campus, method, confidence)
    return summary.log()


# ---------------------------------------------------------------------------
# Reference lists: GTEC, Ministry of Health, Wikipedia (gap-finding only)
# ---------------------------------------------------------------------------
NAME_HINT = re.compile(
    r"(universit|college|polytechnic|institute|school of|nursing|midwi|health|seminary)", re.I
)


class _TableText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._in = [], [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th", "li"):
            self._in, self._cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th", "li") and self._in:
            self._row.append(" ".join("".join(self._cell).split()))
            self._in = False
            if tag == "li":
                self.rows.append(self._row)
                self._row = []
        elif tag == "tr" and self._row:
            self.rows.append(self._row)

    def handle_data(self, data):
        if self._in:
            self._cell.append(data)


def parse_reference_file(path: Path) -> list[dict]:
    """Return [{name, town, category, status}] from a saved CSV/TXT/HTML/PDF list."""
    suffix = path.suffix.lower()
    entries: list[dict] = []
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row.get("name"):
                    entries.append({k: (v or "").strip() for k, v in row.items()})
        return entries
    if suffix in (".txt", ".md"):
        lines = path.read_text(encoding="utf-8").splitlines()
    elif suffix in (".html", ".htm"):
        parser = _TableText()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        lines = [" | ".join(r) for r in parser.rows]
    elif suffix == ".pdf":
        import pdfplumber

        lines = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
    else:
        return entries
    for line in lines:
        text = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        if not text or not NAME_HINT.search(text):
            continue
        parts = [p.strip() for p in re.split(r"\s*[|\t;]\s*", text) if p.strip()]
        name = parts[0]
        town = parts[1] if len(parts) > 1 else ""
        m = re.match(r"(.+?),\s*([A-Z][\w\- ]+)$", name)
        if not town and m:
            name, town = m.group(1).strip(), m.group(2).strip()
        entries.append(
            {
                "name": name,
                "town": town,
                "category": parts[2] if len(parts) > 2 else "",
                "status": "",
            }
        )
    return entries


def _list_meta(path: Path) -> dict:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    lower = path.name.lower()
    if "status" not in meta:
        if "unaccredited" in lower:
            meta["status"] = GtecStatus.UNACCREDITED
        elif "expired" in lower:
            meta["status"] = GtecStatus.EXPIRED
        elif "accredited" in lower or "gtec" in str(path.parent).lower():
            meta["status"] = GtecStatus.ACCREDITED
    return meta


@transaction.atomic
def import_reference_lists(base_dir: Path | None = None) -> Summary:
    base_dir = Path(base_dir or http.RAW_DIR)
    summary = Summary("import_reference_lists", Source.GTEC)
    for source, folder in (
        (Source.GTEC, "gtec"),
        (Source.MOH, "moh"),
        (Source.WIKIPEDIA, "wikipedia"),
    ):
        for path in sorted((base_dir / folder).glob("*")) if (base_dir / folder).exists() else []:
            if path.name.endswith(".meta.json") or path.name.startswith("."):
                continue
            meta = _list_meta(path)
            entries = parse_reference_file(path)
            summary.inc(f"{folder}_entries", len(entries))
            for entry in entries:
                _apply_reference(entry, source, path, meta, summary)
    return summary.log()


def _apply_reference(entry, source, path, meta, summary):
    name = entry["name"]
    source_id = f"{path.name}:{normalise_name(name)}"[:200]
    record = stage(source, "institution", source_id, {**entry, "file": path.name, **meta})
    town = find_town_by_name(entry.get("town", "")) if entry.get("town") else None
    region = town.region if town else None
    match = match_institution(name, None, region, None)
    inst = match.obj
    status = (entry.get("status") or meta.get("status") or "").lower()
    note = f"{meta.get('publisher', source)} {meta.get('published', '')}".strip()
    if inst is not None:
        link_record(record, inst, match.method, match.confidence)
        values = {}
        if source == Source.GTEC and status in GtecStatus.values:
            values["gtec_status"] = status
            values["gtec_note"] = f"{note} ({path.name})"[:300]
        if source in (Source.GTEC, Source.MOH) and inst.kind == "other":
            values["kind"] = classify_kind(name)
        changed = apply_fields(inst, values)
        if save_if_changed(inst, changed, retrieved=False):
            summary.inc(f"{source}_updated")
        else:
            summary.inc(f"{source}_matched")
        return
    # Unmatched: create as unverified with confidence ≤ 0.5 (needs a town for its campus).
    inst = Institution(
        name=name,
        slug=unique_slug(Institution, name),
        kind=classify_kind(name),
        gtec_status=status
        if source == Source.GTEC and status in GtecStatus.values
        else GtecStatus.UNKNOWN,
        gtec_note=f"{note} ({path.name})"[:300] if source == Source.GTEC else "",
        **provenance(
            source, source_id, meta.get("url", ""), 0.4 if source == Source.WIKIPEDIA else 0.5
        ),
    )
    save_if_changed(inst, [])
    link_record(record, inst, "new", inst.confidence)
    summary.inc(f"{source}_created")
    if town is not None:
        campus = Campus(
            institution=inst,
            town=town,
            name=name,
            kind=inst.kind,
            slug=unique_slug(Campus, name),
            **provenance(source, source_id, meta.get("url", ""), inst.confidence),
        )
        save_if_changed(campus, [])
        summary.inc(f"{source}_campuses_created")


# ---------------------------------------------------------------------------
# OSM areas around campuses
# ---------------------------------------------------------------------------
def import_osm_areas_for_campus(campus: Campus, data: dict, summary: Summary) -> None:
    seen = {normalise_name(a.name) for a in Area.objects.filter(campus=campus)}
    town_norm = normalise_name(campus.town.name)
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        norm = normalise_name(name)
        source_id = f"node/{el['id']}"
        stage(Source.OSM, "area", source_id, el)
        if norm == town_norm:
            summary.inc("skipped_same_as_town")
            continue
        area = Area.objects.filter(source=Source.OSM, source_id=source_id, campus=campus).first()
        if area is None and norm in seen:
            summary.inc("skipped_duplicate")
            continue
        created = area is None
        if created:
            area = Area(
                town=campus.town,
                campus=campus,
                name=name,
                slug=unique_slug(Area, f"{name}-{campus.town.name}"),
                review_status=ReviewStatus.UNVERIFIED,
            )
        changed = apply_fields(
            area,
            {
                "lat": el.get("lat"),
                "lng": el.get("lon"),
                **provenance(
                    Source.OSM, source_id, f"https://www.openstreetmap.org/{source_id}", 0.8
                ),
            },
        )
        if save_if_changed(area, changed):
            summary.inc("areas_created" if created else "areas_updated")
        seen.add(norm)


def import_osm_areas(fetcher=None, radius: int | None = None, sleep_s: float = 2.0) -> Summary:
    from constance import config

    radius = radius or config.CAMPUS_AUTOLINK_RADIUS_M
    summary = Summary("import_osm_areas", Source.OSM)
    for campus in Campus.objects.visible().with_point().select_related("town"):
        if fetcher is None:
            query = OSM_AREA_QUERY.format(radius=radius, lat=campus.lat, lon=campus.lng)
            data = http.overpass(query)
            http.save_raw("osm", f"areas-{campus.slug}", data)
            time.sleep(sleep_s)
        else:
            data = fetcher(campus)
        with transaction.atomic():
            import_osm_areas_for_campus(campus, data, summary)
    return summary.log()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def locations_report() -> dict:
    from django.db.models import Count

    campuses = Campus.objects.all()
    total = campuses.count()
    with_point = campuses.with_point().count()
    dupes = possible_duplicates()
    return {
        "regions": Region.objects.count(),
        "regions_with_boundaries": Region.objects.exclude(boundary=None).count(),
        "districts": District.objects.count(),
        "towns": Town.objects.count(),
        "towns_with_points": Town.objects.filter(lat__isnull=False).count(),
        "institutions_by_source": dict(
            Institution.objects.values_list("source").annotate(n=Count("id"))
        ),
        "campuses_by_source": dict(campuses.values_list("source").annotate(n=Count("id"))),
        "campuses": total,
        "campuses_with_points": with_point,
        "campuses_with_points_pct": round(100 * with_point / total, 1) if total else 0,
        "campuses_without_points": list(
            campuses.filter(lat__isnull=True).values_list("name", flat=True)[:50]
        ),
        "unverified_campuses": campuses.filter(review_status=ReviewStatus.UNVERIFIED).count(),
        "unverified_areas": Area.objects.filter(review_status=ReviewStatus.UNVERIFIED).count(),
        "possible_duplicates": [(a.name, b.name, round(s, 2)) for a, b, s in dupes[:50]],
        "gtec_flagged": list(
            Institution.objects.filter(
                gtec_status__in=[GtecStatus.EXPIRED, GtecStatus.UNACCREDITED]
            ).values_list("name", "gtec_status")
        ),
        "match_methods": _match_rates(),
    }


def _match_rates():
    from django.db.models import Count

    from ..models import SourceRecord

    return {
        f"{row['source']}:{row['match_method'] or 'unmatched'}": row["n"]
        for row in SourceRecord.objects.values("source", "match_method").annotate(n=Count("id"))
    }


def possible_duplicates(threshold: float = 0.8):
    items = list(
        Campus.objects.exclude(review_status=ReviewStatus.REJECTED).only("id", "name", "slug")
    )
    norms = [(c, normalise_name(c.name)) for c in items]
    pairs = []
    for i, (a, na) in enumerate(norms):
        for b, nb in norms[i + 1 :]:
            score = trigram_similarity(na, nb)
            if score >= threshold:
                pairs.append((a, b, score))
    pairs.sort(key=lambda p: -p[2])
    return pairs


@transaction.atomic
def merge_campuses(keep: Campus, drop: Campus) -> Campus:
    """Move areas and listings to the kept record, then mark the other rejected."""
    from apps.listings.models import ListingCampus

    Area.objects.filter(campus=drop).update(campus=keep)
    for link in ListingCampus.objects.filter(campus=drop):
        if ListingCampus.objects.filter(listing=link.listing, campus=keep).exists():
            link.delete()
        else:
            link.campus = keep
            link.save(update_fields=["campus"])
    from apps.accounts.models import Profile

    Profile.objects.filter(home_campus=drop).update(home_campus=keep)
    for profile in Profile.objects.filter(followed_campuses=drop):
        profile.followed_campuses.remove(drop)
        profile.followed_campuses.add(keep)
    if not keep.has_point and drop.has_point:
        keep.lat, keep.lng = drop.lat, drop.lng
        keep.save(update_fields=["lat", "lng", "updated_at"])
    if not keep.osm_id and drop.osm_id:
        keep.osm_id = drop.osm_id
        keep.save(update_fields=["osm_id"])
    drop.review_status = ReviewStatus.REJECTED
    drop.is_active = False
    drop.admin_locked = True
    drop.save(update_fields=["review_status", "is_active", "admin_locked", "updated_at"])
    return keep


@transaction.atomic
def merge_institutions(keep: Institution, drop: Institution) -> Institution:
    Campus.objects.filter(institution=drop).update(institution=keep)
    if not keep.wikidata_id and drop.wikidata_id:
        qid = drop.wikidata_id
        drop.wikidata_id = None
        drop.save(update_fields=["wikidata_id"])
        keep.wikidata_id = qid
        keep.save(update_fields=["wikidata_id"])
    drop.review_status = ReviewStatus.REJECTED
    drop.is_active = False
    drop.admin_locked = True
    drop.save(update_fields=["review_status", "is_active", "admin_locked", "updated_at"])
    return keep


# ---------------------------------------------------------------------------
# Network wrappers
# ---------------------------------------------------------------------------
def fetch_wikidata():
    data = http.sparql(WIKIDATA_QUERY)
    http.save_raw("wikidata", "institutions", data)
    qids = [(_value(r, "item") or "").rsplit("/", 1)[-1] for r in data["results"]["bindings"]]
    values = " ".join(f"wd:{q}" for q in qids if q.startswith("Q"))
    campus_data = (
        http.sparql(WIKIDATA_CAMPUS_QUERY % values) if values else {"results": {"bindings": []}}
    )
    http.save_raw("wikidata", "campuses", campus_data)
    return data, campus_data


def fetch_osm(name: str, query: str):
    data = http.overpass(query)
    http.save_raw("osm", name, data)
    return data


def read_text_or_json(path: str):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text) if text.lstrip().startswith(("{", "[")) else io.StringIO(text)
