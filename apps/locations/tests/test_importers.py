"""DATA_SOURCES_PROMPT §11: normalisation, matching, classification, point-in-polygon,
idempotency, locked fields, visibility, merge — all offline against tests/fixtures/sources/."""

from pathlib import Path

import pytest
from django.core.management import call_command

from apps.locations.classify import classify_kind
from apps.locations.importers import http, pipeline
from apps.locations.importers.base import match_institution
from apps.locations.models import Area, Campus, District, Institution, Region, SourceRecord, Town
from apps.locations.services import region_for_point
from tests import factories as f

pytestmark = pytest.mark.django_db
FIX = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sources"


def load(name):
    return http.load_json(FIX / name)


def _snapshot():
    rows = []
    for model in (Region, District, Town, Institution, Campus, Area, SourceRecord):
        for obj in model.objects.order_by("pk"):
            data = {
                fl.attname: getattr(obj, fl.attname)
                for fl in model._meta.concrete_fields
                if fl.attname not in ("updated_at", "created_at")
            }
            rows.append((model.__name__, data))
    return rows


@pytest.fixture
def regions(db):
    fixtureland = f.RegionFactory(name="Fixtureland", slug="fixtureland")
    other = f.RegionFactory(name="Otherland", slug="otherland")
    return fixtureland, other


def run_all(base_dir=None):
    pipeline.import_admin_boundaries(load("hdx_adm1.geojson"), load("hdx_adm2.geojson"))
    pipeline.import_osm_towns(load("overpass_towns.json"))
    pipeline.import_wikidata_institutions(
        load("wikidata_institutions.json"), load("wikidata_campuses.json")
    )
    pipeline.import_osm_campuses(load("overpass_campuses.json"))
    pipeline.import_reference_lists(FIX / "raw")
    areas = load("overpass_areas.json")
    pipeline.import_osm_areas(fetcher=lambda campus: areas)


def test_classification_order():
    assert classify_kind("Sunyani Technical University") == "technical_university"
    assert classify_kind("Berekum College of Education") == "college_of_education"
    assert classify_kind("Nurses and Midwifery Training College") == "nursing_midwifery"
    assert classify_kind("Health Assistants Training School") == "health_training"
    assert classify_kind("Catholic University College of Ghana") == "university_college"
    assert classify_kind("University of Ghana") == "university"
    assert classify_kind("Some Institute") == "other"


def test_boundaries_and_point_in_polygon(regions):
    summary = pipeline.import_admin_boundaries(load("hdx_adm1.geojson"), load("hdx_adm2.geojson"))
    assert summary.counts["regions_updated"] == 2
    fixtureland, other = regions
    assert region_for_point(7.5, -2.5) == fixtureland
    assert region_for_point(5.5, 0.5) == Region.objects.get(pk=other.pk)
    assert region_for_point(20, 20) is None
    assert District.objects.get().region == fixtureland


def test_towns_get_regions_and_skip_outside(regions):
    pipeline.import_admin_boundaries(load("hdx_adm1.geojson"))
    summary = pipeline.import_osm_towns(load("overpass_towns.json"))
    assert summary.counts["skipped_no_region"] == 1
    town = Town.objects.get(name="Fixtureton")
    assert town.region.slug == "fixtureland" and town.source == "osm" and town.has_point


def test_full_import_creates_records_with_provenance(regions):
    run_all()
    inst = Institution.objects.get(wikidata_id="Q900001")
    assert inst.short_name == "FUT" and inst.licence.startswith("CC0") and inst.retrieved_at
    assert not Institution.objects.filter(name="Old Closed College").exists()  # dissolved
    assert SourceRecord.objects.filter(source_id="Q900003").exists()  # but staged
    main = inst.campuses.order_by("pk").first()
    assert main.town.name == "Fixtureton" and main.lat == pytest.approx(
        7.301
    )  # Wikidata coords preferred
    assert main.osm_id == "way/5001"  # matched by OSM wikidata tag
    assert Campus.objects.filter(name__contains="North Campus", institution=inst).exists()
    nursing = Campus.objects.get(name__startswith="Fixtureton Nursing")
    assert (
        nursing.kind == "nursing_midwifery"
        and nursing.confidence <= 0.5
        and nursing.review_status == "unverified"
    )
    for model in (Institution, Campus, Town, Area):
        for obj in model.objects.exclude(source="manual"):
            assert obj.source and obj.licence and obj.retrieved_at and obj.review_status


def test_gtec_flags_and_unaccredited_hidden(regions):
    run_all()
    assert Institution.objects.get(wikidata_id="Q900001").gtec_status == "accredited"
    flagged = Institution.objects.get(name="Fixtureton Technical University")
    assert flagged.gtec_status == "unaccredited"
    assert not Campus.objects.visible().filter(institution=flagged).exists()
    new = Institution.objects.get(name="Brand New College of Education")
    assert new.review_status == "unverified" and new.confidence <= 0.5
    assert Institution.objects.filter(source="moh", kind="health_training").exists()


def test_areas_dedupe_skip_town_name_and_hidden_until_verified(regions):
    run_all()
    names = sorted(Area.objects.values_list("name", flat=True).distinct())
    assert names == ["Sample Junction", "Testville Heights"]
    assert not Area.objects.visible().exists()


def test_reimport_is_idempotent(regions):
    run_all()
    before = _snapshot()
    run_all()
    after = _snapshot()
    diffs = [
        (a[0], k, a[1][k], b[1][k])
        for a, b in zip(before, after, strict=False)
        for k in a[1]
        if a[1][k] != b[1][k]
    ]
    assert not diffs and len(before) == len(after)


def test_locked_fields_survive_reimport(regions):
    run_all()
    campus = Institution.objects.get(wikidata_id="Q900001").campuses.order_by("pk").first()
    campus.lat, campus.lng = 7.5, -2.5
    campus.locked_fields = ["lat", "lng"]
    campus.save()
    inst = campus.institution
    inst.short_name = "Admin Edit"
    inst.admin_locked = True
    inst.save()
    run_all()
    campus.refresh_from_db()
    inst.refresh_from_db()
    assert (campus.lat, campus.lng) == (7.5, -2.5) and inst.short_name == "Admin Edit"


def test_admin_edit_locks_changed_fields(admin_client, regions):
    campus = f.CampusFactory(name="Before", town=f.TownFactory(region=regions[0]))
    data = {
        "institution": campus.institution_id,
        "name": "After",
        "short_name": campus.short_name,
        "slug": campus.slug,
        "kind": campus.kind,
        "town": campus.town_id,
        "is_active": "on",
        "lat": campus.lat,
        "lng": campus.lng,
        "osm_id": "",
        "source": "manual",
        "source_id": "",
        "source_url": "",
        "licence": "",
        "confidence": 1,
        "review_status": "verified",
        "locked_fields": "[]",
    }
    r = admin_client.post(f"/admin/locations/campus/{campus.pk}/change/", data)
    assert r.status_code == 302, r.content[:2000]
    campus.refresh_from_db()
    assert "name" in campus.locked_fields


def test_matching_rules(regions):
    inst = f.InstitutionFactory(name="University of Testing Things", wikidata_id="Q1")
    assert match_institution("whatever", "Q1").confidence == 1.0
    m = match_institution("Univ. of Testing Things")
    assert m.obj == inst and m.confidence == 0.9
    town = f.TownFactory(region=regions[0])
    f.CampusFactory(institution=inst, town=town)
    fuzzy = match_institution("University of Testing Thing", region=regions[0])
    assert fuzzy.obj == inst and fuzzy.confidence == 0.7
    assert match_institution("University of Testing Thing", region=regions[1]).obj is None
    assert match_institution("Completely Different Polytechnic").method == "new"


def test_merge_moves_listings_and_areas(regions):
    keep = f.CampusFactory(name="Merge Keep")
    drop = f.CampusFactory(name="Merge Drop")
    listing = f.ListingFactory()
    f.ListingCampusFactory(listing=listing, campus=drop)
    f.AreaFactory(campus=drop, town=drop.town)
    pipeline.merge_campuses(keep, drop)
    drop.refresh_from_db()
    assert listing.campus_links.get().campus == keep and keep.areas.count() == 1
    assert (
        drop.review_status == "rejected"
        and not Campus.objects.visible().filter(pk=drop.pk).exists()
    )


def test_duplicates_report_and_command(regions, capsys):
    f.CampusFactory(name="Accra Technical Univ")
    f.CampusFactory(name="Accra Technical University")
    assert pipeline.possible_duplicates()
    call_command("locations_report")
    assert "possible_duplicates" in capsys.readouterr().out


def test_seed_locations_idempotent_and_no_coordinates():
    call_command("seed_locations")
    call_command("seed_locations")
    assert Region.objects.count() == 16
    assert Campus.objects.count() == 22
    assert not Campus.objects.filter(lat__isnull=False).exists()


def test_commands_accept_recorded_files(regions):
    call_command("import_admin_boundaries", from_file=str(FIX / "hdx_adm1.geojson"))
    call_command("import_osm_towns", from_file=str(FIX / "overpass_towns.json"))
    call_command("import_wikidata_institutions", from_file=str(FIX / "wikidata_institutions.json"))
    call_command("import_osm_campuses", from_file=str(FIX / "overpass_campuses.json"))
    call_command("import_reference_lists", dir=str(FIX / "raw"))
    call_command("import_osm_areas", from_file=str(FIX / "overpass_areas.json"))
    assert Institution.objects.filter(wikidata_id="Q900001").exists()


def test_no_network_in_tests(monkeypatch):
    import requests

    def boom(*a, **k):
        raise AssertionError("network call in tests")

    monkeypatch.setattr(requests, "request", boom)
    with pytest.raises(AssertionError):
        http.fetch("https://example.test")


def test_osm_departments_and_offices_do_not_become_campuses(regions):
    from apps.locations.importers.pipeline import looks_like_institution

    assert looks_like_institution("Fixtureton Nursing and Midwifery Training College")
    assert looks_like_institution("Accra Business School")
    for name in (
        "Department of Physics",
        "British Council Ghana",
        "Association of African Universities",
        "Volta Hall",
        "Balme Library",
    ):
        assert not looks_like_institution(name), name
    pipeline.import_admin_boundaries(load("hdx_adm1.geojson"))
    pipeline.import_osm_towns(load("overpass_towns.json"))
    data = {
        "elements": [
            {
                "type": "node",
                "id": 9,
                "lat": 7.3,
                "lon": -2.3,
                "tags": {"amenity": "university", "name": "Department of Testing"},
            }
        ]
    }
    assert pipeline.import_osm_campuses(data).counts == {"skipped_not_an_institution": 1}


def test_report_flags_points_far_from_town(regions):
    town = f.TownFactory(lat=7.3, lng=-2.3)
    f.CampusFactory(name="Far Away Campus", town=town, lat=7.7, lng=-2.0)
    f.CampusFactory(name="Close Campus", town=town, lat=7.31, lng=-2.3)
    names = [row[0] for row in pipeline.points_far_from_town()]
    assert names == ["Far Away Campus"]


def test_hdx_lowercase_properties_and_region_alias(db):
    north_east = f.RegionFactory(name="North East", slug="north-east")
    data = {
        "features": [
            {
                "type": "Feature",
                "properties": {"adm1_name": "Northern East", "adm1_pcode": "GH09"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 10], [1, 10], [1, 11], [0, 11], [0, 10]]],
                },
            }
        ]
    }
    pipeline.import_admin_boundaries(data)
    north_east.refresh_from_db()
    assert north_east.hdx_pcode == "GH09" and north_east.boundary


def test_same_name_different_sources_stay_separate(regions):
    pipeline.import_admin_boundaries(load("hdx_adm1.geojson"))
    towns = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 7.1,
                "lon": -2.9,
                "tags": {"place": "town", "name": "Twinville"},
            },
            {
                "type": "node",
                "id": 2,
                "lat": 7.9,
                "lon": -2.1,
                "tags": {"place": "town", "name": "Twinville"},
            },
        ]
    }
    pipeline.import_osm_towns(towns)
    pipeline.import_osm_towns(towns)
    assert Town.objects.filter(name="Twinville").count() == 2
    rows = {
        "results": {
            "bindings": [
                {
                    "item": {"value": f"http://www.wikidata.org/entity/{q}"},
                    "itemLabel": {"value": "Twin University"},
                    "coords": {"value": point},
                }
                for q, point in (("Q801", "Point(-2.9 7.1)"), ("Q802", "Point(-2.1 7.9)"))
            ]
        }
    }
    pipeline.import_wikidata_institutions(rows)
    before = list(Institution.objects.order_by("pk").values_list("wikidata_id", "retrieved_at"))
    pipeline.import_wikidata_institutions(rows)
    assert sorted(Institution.objects.values_list("wikidata_id", flat=True)) == ["Q801", "Q802"]
    assert (
        list(Institution.objects.order_by("pk").values_list("wikidata_id", "retrieved_at"))
        == before
    )


def test_area_import_survives_failed_campus_and_resumes(regions, monkeypatch, tmp_path):
    f.CampusFactory(name="Ok Campus", lat=7.3, lng=-2.3)
    f.CampusFactory(name="Busy Campus", lat=7.4, lng=-2.4)
    monkeypatch.setattr(http, "RAW_DIR", tmp_path)
    calls = []

    def flaky(query):
        calls.append(query)
        if len(calls) == 2:
            raise http.FetchError("504")
        return load("overpass_areas.json")

    monkeypatch.setattr(http, "overpass", flaky)
    summary = pipeline.import_osm_areas(sleep_s=0)
    assert summary.counts["campuses_failed"] == 1 and Area.objects.exists()
    calls.clear()
    summary = pipeline.import_osm_areas(sleep_s=0)
    assert summary.counts["campuses_from_cache"] == 1 and len(calls) == 1


def test_reference_html_table_with_serial_numbers(tmp_path):
    page = tmp_path / "gtec_unaccredited-2026.html"
    page.write_text(
        "<table><tr><th>S/N</th><th>Institution</th><th>Location</th></tr>"
        "<tr><td>1</td><td>Sample Institute of Technology</td><td>Kasoa</td></tr>"
        "<tr><td>2.</td><td>Example College of Health</td><td>Kumasi</td></tr></table>",
        encoding="utf-8",
    )
    entries = pipeline.parse_reference_file(page)
    assert [(e["name"], e["town"]) for e in entries] == [
        ("Sample Institute of Technology", "Kasoa"),
        ("Example College of Health", "Kumasi"),
    ]


def test_merge_moves_osm_id_to_kept_campus(regions):
    keep = f.CampusFactory(name="Keep U", osm_id="")
    drop = f.CampusFactory(name="Drop U", osm_id="way/42")
    pipeline.merge_campuses(keep, drop)
    keep.refresh_from_db()
    drop.refresh_from_db()
    assert keep.osm_id == "way/42" and drop.osm_id == ""
    assert Campus.objects.filter(osm_id="way/42").count() == 1
