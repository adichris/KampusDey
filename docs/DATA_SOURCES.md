# Data sources

Every imported record keeps `source`, `source_id`, `source_url`, `retrieved_at`, `licence`,
`confidence` and `review_status`. Raw responses are staged in `SourceRecord` and cached in
`data/raw/<source>/`, so matching can be re-run offline (`--offline`).

## Part 1 — Location data
| Source | Used for | Licence | How |
|---|---|---|---|
| Wikidata (SPARQL) | institutions, short names, websites, coordinates | CC0 | `import_wikidata_institutions` |
| OpenStreetMap (Overpass) | campus points, towns, neighbourhoods | ODbL — credit "© OpenStreetMap contributors" | `import_osm_campuses`, `import_osm_towns`, `import_osm_areas` |
| HDX COD-AB | region/district polygons | as stated on the dataset page | download GeoJSON to `data/raw/hdx/` (names containing `adm1`, `adm2`), run `import_admin_boundaries` |
| GTEC | accreditation status | public regulator information | save lists to `data/raw/gtec/` (CSV/TXT/HTML/PDF; file names containing `unaccredited`/`expired` set that status), run `import_reference_lists` |
| Ministry of Health (KNUST PDF) | nursing/health colleges | public document | save PDF to `data/raw/moh/`, run `import_reference_lists` |
| Wikipedia | gap-finding only (names, towns) | facts only | save HTML to `data/raw/wikipedia/` |

Optional sidecar `<file>.meta.json` with `{"publisher", "published", "url", "status"}`.

Trust order: admin edits → GTEC/MoH → Wikidata → OSM → Wikipedia. Wikidata coordinates are
preferred; OSM only fills missing points.

Matching: same Wikidata ID (1.0) → normalised name (0.9) → trigram ≥ 0.85 within the same region
or 5 km (0.7) → otherwise a new `unverified` record (≤ 0.5).

### Running
```
make import-locations          # seed + all importers + report (needs internet)
manage.py import_locations --offline   # re-run from cached raw files
manage.py locations_report
```
Re-running never overwrites a field listed in `locked_fields` or anything on an `admin_locked`
record. Editing a record in the admin locks the edited fields automatically.

### Adding a missing campus by hand
Admin → Locations → Campuses → Add. Set the town, kind and (if known from a source) the point,
with `source = manual`. Or approve a user's *My school isn't listed* request (Campus requests →
"Approve and create campus").

### Refresh
Quarterly (beat): Wikidata, OSM campuses and areas, then the report; superadmins are notified of
new unverified campuses. GTEC/MoH lists are refreshed manually when new lists are published.

## Part 2 — External content
Sources live in **External content → Source registry** and run only when *approved* and *enabled*,
never more often than `min_interval_minutes`. Approval requires ticking "I have reviewed the terms".
Suspending a source hides all of its content immediately.

| Source | Terms | Refresh |
|---|---|---|
| OpenStreetMap places (Overpass, 2 km around each campus) | ODbL; attribution on every card | every `PLACES_REFRESH_DAYS` (30); missing twice → removed; claimed places never changed |
| Remotive remote jobs | link back and name Remotive on every job; ≤ 4 fetches/day (code-enforced); no sign-up gates; never in JobPosting data, sitemaps, emails or alerts | `REMOTIVE_FETCHES_PER_DAY` (default 2) |
| Partner feeds (JSON/RSS) | only with the publisher's written permission, recorded on the source | per source |

Phone numbers of OSM places are imported only when `IMPORT_PLACE_PHONES` is on (default off).
`make import-external` runs every approved source once.

We never scrape listings, prices or personal details from other platforms.
