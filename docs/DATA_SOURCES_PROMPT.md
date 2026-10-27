# KampusDey — Real Data: Sources and Import Prompt (for Codex)

> **How to use this file**
> Commit it as `docs/DATA_SOURCES_PROMPT.md`. It covers two milestones:
> - **Part 1 — Milestone M1.5 (location data)**, after M1 is accepted: **"Read AGENTS.md and docs/DATA_SOURCES_PROMPT.md. Build Milestone M1.5, then stop and report."**
> - **Part 2 — Milestone M9.5 (external content: places around campus and remote jobs)**, after M9 (Hostel Manager) is accepted: **"Read AGENTS.md and docs/DATA_SOURCES_PROMPT.md. Build Milestone M9.5, then stop and report."**
>
> The import commands need internet access. If your Codex environment has internet disabled, Codex should still build and test everything against the recorded sample responses in `tests/fixtures/sources/`, and you run the real imports locally with `make import-locations` and `make import-external`.

---

## 1. Goal

Populate KampusDey's location data (regions, towns, institutions, campuses and neighbourhoods around campuses) from **real, public, sourced data** instead of hand-typed lists, so the location picker, campus auto-linking and "nearby" features work across Ghana from day one.

Then (Part 2) bring the platform up to speed with **external content that its sources allow KampusDey to reuse**: hotels, guest houses and local businesses around each campus from OpenStreetMap (as unclaimed places their owners can claim), and remote jobs from Remotive's public API.

Every imported record must carry its source, licence and review status, so admins can verify it and the import can be re-run safely.

---

## 2. Rules

1. **Only the sources in this file.** Part 1: institutions, campuses, towns, regions, neighbourhoods and their coordinates. Part 2: OpenStreetMap places (accommodation and businesses) and remote jobs from Remotive, plus partner feeds an admin has approved.
2. **Never scrape listings or people.** Do not collect listings, prices, phone numbers, names or photos from Jiji, UniMarketGH, Jobberman or other job boards, Booking.com, Airbnb, hostel sites, WhatsApp groups or any other platform. No HTML scraping of any website. New job or listing feeds are added only through official APIs or feeds with the owner's permission (§14).
3. **Provenance on every record:** source, source ID, source URL, retrieval date, licence, confidence, review status.
4. **Respect each source's terms:** identify the importer with a proper User-Agent (`KampusDey-DataImport/1.0 (+<SITE_URL>/contact)`), throttle requests, back off on HTTP 429/5xx, cache raw responses, and never hammer public APIs.
5. **Admins have the final word.** Re-running an import must never overwrite fields an admin has edited or locked.
6. **Idempotent.** Running any import twice produces the same database state.
7. **External content is always labelled.** It carries a source badge and attribution, stays separate from user posts in ranking, and is never boostable.

---

# Part 1 — Location data (Milestone M1.5)

## 3. Sources

| # | Source | What to take | Licence / terms | Access |
|---|---|---|---|---|
| 1 | **Wikidata Query Service** — https://query.wikidata.org/ | Higher-education institutions in Ghana: name, short name, coordinates, located-in (town/district), official website, instance-of types, dissolved date, Wikidata ID | **CC0** (no attribution required; still record the source) | SPARQL endpoint `https://query.wikidata.org/sparql` (query in §4.1). A check on 26 Oct 2026 returned **293** institutions, **209** with coordinates |
| 2 | **OpenStreetMap via Overpass API** — https://overpass-api.de/api/interpreter | Campus points/outlines (`amenity=university` / `amenity=college`), towns (`place=city/town`), neighbourhoods near campuses (`place=suburb/neighbourhood/quarter/village/hamlet`), `wikidata=*` tags for matching | **ODbL**: credit "© OpenStreetMap contributors" wherever OSM-derived data is shown; derived databases have share-alike obligations, so keep OSM-derived records flagged and check obligations before redistributing the data | Overpass QL (queries in §4.2); follow the Overpass fair-use guidance |
| 3 | **Ghana – Subnational Administrative Boundaries (COD-AB) on HDX** — https://data.humdata.org/m/dataset/cod-ab-gha | Region (admin 1) and district (admin 2) polygons and official names, for assigning towns and campuses to regions | Licence stated on the dataset page — record it and attribute as required | Download GeoJSON/Shapefile once into `data/raw/hdx/` |
| 4 | **Ghana Tertiary Education Commission (GTEC)** — https://gtec.edu.gh | Official lists of accredited institutions, plus GTEC notices naming unaccredited institutions and those with expired accreditation | Public regulator information (facts); cite the source | Save each published list (HTML/PDF) into `data/raw/gtec/` with its publication date; parse names and categories. Newspaper reprints of GTEC lists (e.g. Daily Graphic) can be used as a fallback copy |
| 5 | **Ministry of Health training institutions list (KNUST affiliation PDF, 2026)** — https://www.knust.edu.gh/sites/default/files/2026-02/MINISTRY%20OF%20HEALTH%20TRAINING%20INSTITUTIONS%20AFFILIATED%20TO%20KNUST.pdf | Names and towns of nursing, midwifery and health training colleges | Public document (facts); cite the source | Download into `data/raw/moh/`; parse with `pdfplumber` |
| 6 | **Wikipedia lists** — e.g. "List of universities in Ghana", "List of colleges of education in Ghana", "List of Nursing Training Colleges in Ghana" | Cross-check only: names, towns and Wikidata IDs, to find institutions missing from sources 1–5 | Text is **CC BY-SA**: take facts only (names, towns), never copy descriptions | MediaWiki API (`action=parse`) or saved HTML in `data/raw/wikipedia/` |
| 7 | **Official institution websites** (from Wikidata `P856`) | Manual verification by admins: current name, campuses, logo permission | Each site's own terms; no bulk scraping | Linked from the admin review screen |

**Order of trust when sources disagree:** admin edits → GTEC / Ministry of Health (names and status) → Wikidata (IDs, websites, coordinates) → OSM (coordinates, outlines, neighbourhoods) → Wikipedia (gap-finding only). Prefer **Wikidata coordinates** (CC0) over OSM when both exist.

---

## 4. Queries

### 4.1 Wikidata — institutions in Ghana

```sparql
SELECT ?item ?itemLabel (SAMPLE(?short) AS ?shortName) (SAMPLE(?coord) AS ?coords)
       (SAMPLE(?admLabel) AS ?adm) (SAMPLE(?website) AS ?site)
       (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types)
       (SAMPLE(?dissolved) AS ?diss) WHERE {
  ?item wdt:P17 wd:Q117 .                       # country: Ghana
  ?item wdt:P31/wdt:P279* wd:Q38723 .           # instance of (a subclass of) higher education institution
  OPTIONAL { ?item wdt:P1813 ?short . FILTER(LANG(?short) = "en") }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P131 ?admE . ?admE rdfs:label ?admLabel . FILTER(LANG(?admLabel) = "en") }
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P31 ?type . ?type rdfs:label ?typeLabel . FILTER(LANG(?typeLabel) = "en") }
  OPTIONAL { ?item wdt:P576 ?dissolved }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
GROUP BY ?item ?itemLabel
```

- Coordinates come back as WKT `Point(lon lat)`; note the order.
- Skip items with a dissolved date (`P576`), but keep them in the staging table for reference.
- Add a second query for campuses of multi-campus institutions: items with `P749` (parent organization) or `P361` (part of) pointing to an imported institution.

### 4.2 OpenStreetMap — campuses, towns and neighbourhoods

Campuses (one country-wide query):

```
[out:json][timeout:180];
area["ISO3166-1"="GH"][admin_level=2]->.gh;
nwr["amenity"~"^(university|college)$"]["name"](area.gh);
out center tags;
```

Towns and cities:

```
[out:json][timeout:180];
area["ISO3166-1"="GH"][admin_level=2]->.gh;
node["place"~"^(city|town)$"](area.gh);
out tags;
```

Neighbourhoods around one campus (run per campus with a point; radius = `CAMPUS_AUTOLINK_RADIUS_M`, default 3000; sleep ≥ 2 s between requests):

```
[out:json][timeout:60];
node["place"~"^(suburb|neighbourhood|quarter|village|hamlet)$"]["name"](around:3000,{lat},{lon});
out tags;
```

Use the OSM `wikidata=*` tag to match OSM objects to Wikidata institutions before any name matching.

---

## 5. Data model changes

Add to the `locations` app (migrations, admin, factories, tests):

- **Institution**: `name`, `short_name`, `kind`, `website`, `wikidata_id` (unique, null), `gtec_status` [accredited, expired, unaccredited, unknown], `is_active`.
- **Campus** gains `institution` (FK Institution). An institution can have several campuses (e.g. UENR's Sunyani, Dormaa Ahenkro and Nsoatre campuses).
- **Campus kinds** become: `university`, `university_college`, `technical_university`, `college_of_education`, `nursing_midwifery`, `health_training`, `other`.
- **Region** gains `boundary` (MultiPolygon) and `hdx_pcode`. Optionally add **District** (`region`, `name`, `boundary`, `hdx_pcode`).
- **Provenance fields** (abstract mixin) on Region, District, Town, Institution, Campus and Area: `source` [wikidata, osm, hdx, gtec, moh, wikipedia, manual], `source_id`, `source_url`, `retrieved_at`, `licence`, `confidence` (0–1), `review_status` [unverified, verified, rejected], `admin_locked` (bool), `locked_fields` (JSON list).
- **SourceRecord** (staging): `source`, `source_id`, `raw` (JSON), `retrieved_at`, `matched_content_type` + `matched_object_id` (generic FK, null), `match_method`, `match_score`. Raw data is kept so matches can be re-run without new network calls.

---

## 6. Pipeline

Management commands in `apps/locations/importers/`, each idempotent, each printing a summary report:

| Command | Does |
|---|---|
| `import_admin_boundaries` | Loads HDX region (and district) polygons; links to the 16 seeded regions by name/P-code |
| `import_wikidata_institutions` | Runs §4.1, writes SourceRecords, creates or updates Institutions and main Campuses |
| `import_osm_campuses` | Runs the campus query, writes SourceRecords, matches to campuses (by `wikidata` tag first), fills missing points |
| `import_osm_towns` | Runs the towns query; creates Towns with points; assigns Region by point-in-polygon |
| `import_reference_lists` | Parses saved GTEC, Ministry of Health and Wikipedia files from `data/raw/`; matches by name; sets `gtec_status`; creates unmatched institutions as `unverified` with `confidence` ≤ 0.5 |
| `import_osm_areas` | For each campus with a point, fetches nearby neighbourhoods and creates Areas linked to the campus and town |
| `locations_report` | Prints counts per source, match rates, campuses without points, possible duplicates, institutions flagged by GTEC |
| `import_locations` | Runs all of the above in order (`make import-locations`) |

**Matching rules**

1. Same Wikidata ID (from Wikidata or OSM `wikidata` tag) → match, confidence 1.0.
2. Normalised name equality → confidence 0.9. Normalise: lowercase, strip punctuation and accents, `&` → `and`, expand common abbreviations (`univ` → `university`, `tech` → `technical`, `coll` → `college`, `n&m`/`nmtc` → `nurses and midwifery training college`), collapse whitespace.
3. Trigram similarity ≥ 0.85 **and** (same region **or** distance ≤ 5 km) → confidence 0.7, `unverified`.
4. Anything else → new record, `unverified`, confidence ≤ 0.5.

**Classification** of `kind`, in this order: name contains "Technical University" → `technical_university`; "College of Education" → `college_of_education`; "Nursing", "Midwifery" → `nursing_midwifery`; "Health", "Medical Assistants", "Health Assistants" → `health_training`; "University College" → `university_college`; "University" → `university`; else `other`. Admins can correct it.

**Town and region assignment:** Region by point-in-polygon on HDX boundaries; Town from the nearest OSM `place=city/town` within 15 km, else Wikidata `P131`. Never guess a point that no source provides.

**Areas:** skip names identical to the town; deduplicate by normalised name per campus; store points; default `review_status = unverified`.

**Visibility rules:**
- `rejected` records and institutions with GTEC status `unaccredited` never appear to users.
- `unverified` campuses appear in the picker, with a dashboard counter so admins work through them.
- `unverified` areas are hidden from users until verified.

**Never overwrite** a field listed in `locked_fields` or any field on a record with `admin_locked = True`. Admin edits in the admin automatically add the edited fields to `locked_fields`.

---

## 7. Admin review screens

- **Locations review queue** (unfold): unverified institutions, campuses and areas with source links, confidence, a mini Leaflet map with the point, and bulk actions *Verify*, *Reject*, *Merge into…* (merge moves campuses, areas and listings to the kept record).
- **Duplicates view:** pairs with similarity ≥ 0.8 for quick merge decisions.
- **GTEC flags:** institutions marked `expired` or `unaccredited`, with the source notice and date.
- Dashboard tiles: unverified campuses, campuses without points, unverified areas, flagged institutions.

---

## 8. Attribution and documentation

- Wherever OSM-derived points or areas are shown (location picker, campus pages, maps), display "Location data © OpenStreetMap contributors" (the map attribution already covers map views).
- Add a **Data sources** page (`/about/data-sources/`) listing each source, its licence and the last import date.
- Write `docs/DATA_SOURCES.md`: sources, licences, refresh procedure, how to add a missing campus by hand, how to re-run imports safely.

---

## 9. Refresh

- Celery beat runs `import_wikidata_institutions`, `import_osm_campuses` and `import_osm_areas` **quarterly** (off-peak), then `locations_report`, and notifies superadmins of new unverified records.
- GTEC and Ministry of Health lists are refreshed manually when new lists are published: save the file to `data/raw/` and run `import_reference_lists`.

---

## 10. Other real data to start with

- **Categories:** use the item and service categories in the build prompt.
- **Price ranges for moderation:** admins set the first `min_price`/`max_price` per category by hand. Later, a monthly task suggests ranges from KampusDey's own listings (5th–95th percentile, minimum 30 samples) for admins to accept. It never applies them automatically and never uses other platforms' data.
- **Rent check:** comes only from KampusDey's own listings (§6.13 of the build prompt).

---

## 11. Tests

- Recorded sample responses in `tests/fixtures/sources/` (a small Wikidata result, an Overpass campus result, an Overpass neighbourhood result, a trimmed HDX GeoJSON, a short GTEC list excerpt). Tests never call the network.
- Test: normalisation, each matching rule, classification, point-in-polygon region assignment, idempotency (run twice → no changes), `locked_fields` protection, visibility rules, merge action.

---

## 12. Acceptance criteria (M1.5)

1. On a fresh database, `make import-locations` completes and `locations_report` shows: 16 regions with boundaries; institutions from Wikidata, OSM and the reference lists; the share of campuses with points; duplicates flagged; GTEC flags applied.
2. Sunyani institutions (UENR, Sunyani Technical University, Catholic University of Ghana, Berekum College of Education, the Sunyani nursing and midwifery college) exist with towns and regions, and points where any source provides them.
3. Every imported record has source, licence, retrieval date and review status.
4. Running the import a second time changes nothing; admin-edited fields survive re-imports.
5. No listing, price, person or contact detail from any third-party platform is in the database.
6. Tests pass without network access; `docs/DATA_SOURCES.md` and the Data sources page exist.


---

# Part 2 — External content (Milestone M9.5)

## 13. Goal

Make KampusDey useful from launch day in sections that would otherwise start empty:

- **Short stays and Rooms & Hostels:** hotels, guest houses, hostels, motels and serviced apartments near each campus.
- **Services and an "Around campus" directory:** printing and copy shops, salons and barbers, phone and computer repair shops, laundries, restaurants, chop bars, cafés, pharmacies and supermarkets near each campus.
- **Jobs:** remote jobs and online gigs suitable for students.

All of it comes only from sources whose terms allow reuse, through a **Source registry** an admin controls.

## 14. Source registry (new app `apps/external/`)

- **ExternalSource**: `name`, `slug`, `kind` [osm_places, remotive_jobs, partner_feed], `base_url`, `terms_url`, `licence`, `attribution_text`, `permission_status` [pending_review, approved, suspended], `approved_by`, `approved_at`, `enabled`, `min_interval_minutes`, `config` (JSON), `last_run_at`, `last_status`.
- **ExternalRun**: `source`, `started_at`, `finished_at`, `status` [ok, partial, failed], `created`, `updated`, `removed`, `error`.
- A source runs **only** when `permission_status = approved` and `enabled = True`, and never more often than `min_interval_minutes`. Setting a source to `suspended` hides all its content immediately.
- Admin: source list with **Run now**, run history, and a required "I have reviewed the terms at `terms_url`" confirmation before approval.
- Seed two sources as `pending_review`: **OpenStreetMap places** and **Remotive remote jobs**. An admin approves them after reading the terms.
- **Partner feeds** (RSS, Atom or JSON) are added only after the publisher gives written permission; store a note of that permission in the source record. Good candidates to approach: Ghanaian job boards, university career offices, NGOs and employers. Never scrape HTML pages.

## 15. Places around campus (OpenStreetMap)

### 15.1 Model

**Place** (with the provenance mixin from §5): `name`, `slug`, `kind` [hotel, guest_house, hostel, motel, apartment, copyshop, hairdresser, beauty, phone_repair, computer_repair, laundry, restaurant, fast_food, cafe, pharmacy, supermarket, other], `town`, `campuses` (M2M with distance), `location` (point), `address`, `website`, `opening_hours` (raw OSM string), `phone` (only if `IMPORT_PLACE_PHONES` is on; default **off**), `source` (FK ExternalSource), `source_id` (`node/123`, `way/456`), `source_url` (openstreetmap.org link), `last_seen_at`, `missing_count`, `status` [unclaimed, claim_pending, claimed, hidden, removed], `owner` (FK User, null), `hostel` (FK Hostel, null).

### 15.2 Import (`import_osm_places`)

For each campus with a point, one Overpass query (radius `CAMPUS_PLACES_RADIUS_M`, default 2000; sleep ≥ 2 s between queries):

```
[out:json][timeout:60];
(
  nwr["tourism"~"^(hotel|guest_house|hostel|motel|apartment)$"]["name"](around:2000,{lat},{lon});
  nwr["shop"~"^(copyshop|hairdresser|beauty|mobile_phone|computer|electronics|laundry|dry_cleaning|supermarket|convenience)$"]["name"](around:2000,{lat},{lon});
  nwr["amenity"~"^(restaurant|fast_food|cafe|food_court|pharmacy)$"]["name"](around:2000,{lat},{lon});
);
out center tags;
```

- Map OSM tags to `kind` (e.g. `shop=mobile_phone` → `phone_repair`, `shop=copyshop` → `copyshop`, `shop=laundry` or `dry_cleaning` → `laundry`).
- Deduplicate across campuses by OSM ID; link each place to every campus within the radius.
- Refresh every `PLACES_REFRESH_DAYS` (default 30). A place missing from two consecutive refreshes becomes `removed`. Claimed places are never changed by refreshes.
- Never invent prices, ratings, photos or descriptions. Places show what OSM provides and nothing more.

### 15.3 Where places appear

- An **"Around campus" directory** per campus (`/<campus-slug>/around/`) with category tabs, list and map, and an OSM attribution line.
- In **Short stays** and **Rooms & Hostels**: accommodation places in a separate block below user listings, titled "Other places nearby", labelled "From OpenStreetMap — not verified, prices not listed". Never mixed into ranking or boosted slots.
- In **Services**: matching business places in a similar block (copy shops under printing, salons under hair, repair shops under repairs, laundries under laundry).
- Place cards show a **"From OpenStreetMap"** badge, distance and walking minutes, and buttons for **Website** (if present), **Directions** (opens the map) and **Claim this place**.
- Users can **report** a place ("Closed", "Wrong location", "Not a real place"); 3 reports hide it pending review.
- Telemetry records views and taps on places with `meta.place_id`.

### 15.4 Claim flow

1. A logged-in, verified user taps **Claim this place** and chooses a proof: a photo of themselves at the premises with the signboard visible, or a business registration document (private storage, deleted after review, like VerificationRequest documents in the build prompt).
2. The place becomes `claim_pending`; the claim appears in the admin claim queue.
3. On approval the user becomes `owner`; status becomes `claimed`; the badge changes to **"Claimed by owner"**.
   - Accommodation kinds: a **Hostel** (Hostel Manager) is created pre-filled with the name and location, so the owner can add room types and real prices.
   - Business kinds: the owner can edit the place page, add a phone number and opening hours, and post Services listings that show on the place page.
4. Rejected claims notify the user with the reason.

## 16. Remote jobs (Remotive)

### 16.1 Terms to follow (from Remotive's public API documentation)

- Endpoint: `https://remotive.com/api/remote-jobs` (optional `category`, `search`, `limit` parameters).
- **Link back** to each job's Remotive URL and **name Remotive as the source** on every job.
- Fetch **at most 4 times a day**; more than 2 requests per minute are blocked. Jobs arrive 24 hours delayed.
- **Do not use the jobs to collect sign-ups or email addresses**, and **do not submit them to other job sites or Google Jobs**.

### 16.2 Model and import (`import_remotive_jobs`)

- **ExternalJob**: `source` (FK ExternalSource), `source_id`, `title`, `company`, `category`, `job_type`, `candidate_location`, `salary_text`, `tags`, `published_at`, `url`, `first_seen_at`, `last_seen_at`, `status` [active, expired, hidden].
- Runs `REMOTIVE_FETCHES_PER_DAY` times a day (default 2, hard maximum 4).
- Keeps only jobs whose `candidate_required_location` matches `REMOTIVE_LOCATION_KEYWORDS` (default `worldwide,anywhere,africa,ghana,emea`) and whose category is in `REMOTIVE_CATEGORIES` (admin-editable).
- A job missing from the feed, or older than `EXTERNAL_JOB_MAX_AGE_DAYS` (default 30), becomes `expired`.
- Do not store or display the full job description; show the summary fields and a link.

### 16.3 Display rules

- A **"Remote jobs"** tab in the Jobs section, separate from local jobs and never mixed into local ranking.
- Each card shows title, company, job type, location requirement, tags, salary if given, posted date, a **"via Remotive"** badge, and a **"View and apply on Remotive"** button that links straight to the Remotive URL (`rel="noopener nofollow"`, new tab).
- **Visible without login.** No sign-up prompts, modals or gates on or around these jobs.
- **Excluded** from: JobPosting structured data, sitemaps (pages carry `noindex`), email digests, saved-search alerts and push notifications.
- The tab header shows "Remote jobs provided by Remotive" with a link.

## 17. Settings (constance)

| Key | Default |
|---|---|
| CAMPUS_PLACES_RADIUS_M | 2000 |
| PLACES_REFRESH_DAYS | 30 |
| IMPORT_PLACE_PHONES | False |
| PLACE_REPORTS_AUTO_HIDE | 3 |
| REMOTIVE_FETCHES_PER_DAY | 2 (maximum 4, enforced in code) |
| REMOTIVE_LOCATION_KEYWORDS | `worldwide,anywhere,africa,ghana,emea` |
| REMOTIVE_CATEGORIES | `customer-support,writing,design,software-dev,data,marketing,sales` (verify slugs against the API) |
| EXTERNAL_JOB_MAX_AGE_DAYS | 30 |

## 18. Admin

- Source registry, run history and **Run now** (respecting the minimum interval).
- **Claim queue** with proof preview, approve/reject and reason.
- Places list with filters (campus, kind, status), hide, merge duplicates, and a map preview.
- External jobs list with hide.
- Dashboard tiles: places per campus, unclaimed vs claimed, pending claims, active remote jobs, last run status per source.

## 19. Tests

- Recorded responses in `tests/fixtures/sources/`: an Overpass places result and a Remotive jobs result. No network calls in tests.
- Test: a source that is not approved never runs; suspending a source hides its content; minimum interval enforced; Remotive fetch cap of 4 a day enforced; tag-to-kind mapping; deduplication across campuses; removal after two missed refreshes; claimed places untouched by refreshes; claim flow end to end, including Hostel creation and proof deletion; place phones not imported when the setting is off; external jobs visible to guests; external jobs absent from JSON-LD, sitemaps, digests and alerts; attribution rendered on every card.

## 20. Acceptance criteria (M9.5)

1. With both sources approved, `make import-external` fills the Around campus directory, the "Other places nearby" blocks and the Remote jobs tab for every campus that has a point.
2. Nothing is fetched from a source that is not approved and enabled.
3. Every external item shows its source badge and attribution; none appear in boosted slots or ranking with user posts.
4. A place can be claimed, approved, and turned into a Hostel or business page by its owner.
5. Remote jobs follow every Remotive term in §16.1.
6. Re-running the imports is idempotent; claimed places and admin edits survive.
7. Tests pass without network access; `docs/DATA_SOURCES.md` is updated with Part 2 sources, terms and refresh schedule, and the Data sources page lists them.
