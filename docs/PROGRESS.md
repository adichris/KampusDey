# KampusDey — Progress

## Status (2026-10-27)

All milestones M0–M14 are implemented in code and covered by tests. **268 tests pass** (offline,
recorded sample responses only); `ruff check` and `ruff format --check` are clean;
`makemigrations --check` reports no changes; `manage.py check --deploy` (prod settings) is clean.
Coverage: 84% overall; services/selectors ≈ 85% combined (contacts 76%, locations 77%,
notifications 74% individually).

Verified by hand in the browser at 375 px: first-visit "Where are you?" sheet, campus home with
feeds and section chips, listing page with sticky contact bar, sign-in, post picker (Trips hidden),
wizard step 2 with Leaflet map and OSM attribution — no console or CSP errors.

| Milestone | State | Notes |
|---|---|---|
| M0 Foundation & theming | done | venv instead of Docker/uv (user request); brand themes + 11 daisyUI themes; no-flash theme script |
| M1 Locations | done | picker, campus switcher, follow, campus requests, GeoIP hint, `update_geolite2` |
| M1.5 Real location data | done — real import run 2026-10-27 | see *Real import results* below. Admin review of unverified records still to do |
| M2 Accounts & verification | done | allauth (mandatory verification), Google optional, staff TOTP, Turnstile, OTP behind runtime switch, encrypted secrets |
| M3 Listing core | done | wizard with drafts, EXIF stripping, WebP renditions, pHash, snapping, auto-link, phone reveal |
| M4 All sections | done | 18 sections, per-campus availability matrix, trips off by default |
| M5 Discovery & maps | done | feeds, filters, sorts incl. distance, search with facets, boosted rotation, Nearby with rings |
| M6 Lifecycle & boosts | done | time-travel tests for every transition, one-tap signed links, boost limits |
| M7 Engagement | done | masked comments, likes/saved, reviews, reports, saved-search alerts, share |
| M8 Chat, notifications, PWA | done | aliases, polling, scam banner, blocks, batched email, web push, service worker |
| M9 Hostel Manager | done | availability stepper drives taken/active |
| M9.5 External content | done (offline-tested) | source registry, OSM places, claim → Hostel, Remotive tab. **Sources still `pending_review`** |
| M10 Moderation & safety | done | rules engine, queue, CSP (nonce, no unsafe-inline), ratelimit, axes, auditlog |
| M11 Telemetry | done | buffer + flush, dedupe, bot filter, roll-ups, retention, admin dashboard |
| M12 Growth & SEO | done | referrals, digest, rent check, spotlight, sitemaps, OG, JSON-LD |
| M13 Admin & ops | done | unfold sidebar/dashboard, constance groups, integration test actions, OPERATIONS.md |
| M14 Hardening | partly | prod settings, Dockerfile, backup script, CI. See known gaps |

## Real import results (2026-10-27, local dev DB)
Sources: HDX COD-AB (GSS, CC BY-IGO), OSM via overpass-api.de, Wikidata SPARQL, GTEC unaccredited
and unrecognized lists (saved under `data/raw/`, gitignored).

| Check (DATA_SOURCES §12) | Result |
|---|---|
| 16 regions with boundaries | ✓ 16/16, plus 260 districts |
| Institutions from Wikidata, OSM, reference lists | ✓ 291 Wikidata, 105 OSM, 104 GTEC-only (flags) |
| Share of campuses with points | ✓ 324 of 335 (96.7%) |
| Duplicates flagged | ✓ 28 pairs in the Duplicates view |
| GTEC flags applied | ✓ 106 institutions flagged unaccredited (hidden from users). GTEC's *accredited* page is currently broken (unrendered shortcode), so no institution is marked accredited yet |
| Sunyani: UENR, STU, Berekum CoE | ✓ matched to seeded records, Wikidata point, OSM id, town and region |
| Sunyani: Catholic University of Ghana | ✓ (after admin merge) three records merged into `cug`: Wikidata Q1051100 + point, OSM way/171357580, Fiapre/Bono; verified and locked |
| Sunyani: NMTC Sunyani | ✓ town and region; **no point**: Wikidata's coordinate is near Wenchi (and says Bono East) while also saying "located in Sunyani", and OSM has no feature for it, so the wrong point was cleared and locked rather than guessed. Fix upstream in Wikidata/OSM, then unlock `lat`/`lng` |
| Provenance on every imported record | ✓ 0 non-manual records missing source/licence/date/status |
| Re-run changes nothing | ✓ towns, Wikidata, OSM campuses and GTEC re-run with zero field changes |
| No third-party listings/people | ✓ by design (only the listed sources) |
| Offline tests, DATA_SOURCES.md, Data sources page | ✓ |

Neighbourhoods: 2,929 areas imported (all `unverified`, hidden until reviewed); 7 campuses still
failed on Overpass 502s — re-run `manage.py import_osm_areas` (it resumes from today's cache).

Fixes made while running for real: current HDX property names and "Northern East" spelling;
Overpass `out body` (the spec's `out tags` returns no node coordinates); OSM departments/halls/
offices skipped; same-name records from different Wikidata items or OSM nodes kept separate;
imports never move an existing campus between towns; duplicate SPARQL rows de-duplicated; area
import survives failed campuses and resumes; GTEC table serial numbers stripped.

## Decisions
- **No Docker locally** (user request): Python venv + pip (`requirements*.txt`) instead of uv;
  `make.ps1` mirrors the Makefile for Windows. Dockerfile/compose kept for later.
- **No PostGIS/GDAL**: points stored as `lat`/`lng`; haversine/SQL distance (`apps/core/geo.py`);
  GeoJSON boundaries with pure-Python point-in-polygon. Swapping to PostGIS later only touches `geo`.
- **SQLite default, PostgreSQL via `DATABASE_URL`**; full-text search uses `SearchVector` on
  PostgreSQL and `icontains` on SQLite. Trigram similarity and pHash implemented in Python.
- **No Redis required**: DB cache; Celery eager without a broker; `manage.py run_periodic --loop`
  replaces beat; telemetry buffer falls back to a `PendingEvent` table.
- Notifications built in-house instead of django-notifications-hq.
- Tailwind built with npm `@tailwindcss/cli` + `daisyui` (allowed fallback in §3).
- Integration secrets cached only in-process; auditlog excludes secret fields and remote addresses.
- External-content FKs named `external_source` (avoids clashing with the provenance `source` field).
- Remotive category slugs mapped to Remotive's display names (`CATEGORY_ALIASES`).
- Test fixtures in `tests/fixtures/sources/` are synthetic, shape-only samples (clearly labelled),
  not recorded real responses — no real-world data is invented in the database.
- Desktop layout uses the full window width beside the sidebar (user request; supersedes the
  "centred column max ~1200px" in §7.1).
- Message admin is intentionally not registered: admins read conversations only through reports.
- "Best time to contact" is a day choice + time range, stored compactly on
  `ContactCard.preferred_time` (e.g. `weekdays 17:00-20:00`, see `apps/contacts/hours.py`) and
  rendered in the viewer's language; older free-text values are still shown as typed.
- Listing photo gallery uses a fixed-height frame (4:3 on phones, `min(68vh, 34rem)` on desktop);
  photos are `object-contain` over a blurred copy, so mixed portrait/landscape photos never
  change the page height. Tap a photo for full screen; arrows, thumbnails, swipe and keys work.
- Sellers pick a main contact button (`ContactCard.preferred_channel`); it is shown first and
  filled, the others outlined (icon-only in the phone bar). In-app chat is the default. The chat
  button posts straight to `chat:start` (the old tap-redirect hit a POST-only view).
- **Guest chat** (owner opt-in, `ContactCard.allow_guest_chat`, off by default; extends §6.8 at the
  user's request): guests give a name, an optional email and a message, then chat through a private
  link (`/chat/g/<key>/`, remembered in a signed cookie). Guarded by per-IP rate limits, banned-term
  checks, Turnstile when configured and blocking. After `GUEST_CHAT_MESSAGE_LIMIT` (constance,
  default 10) messages the guest must sign up or log in; the chat then moves into the account
  (claim link, or automatically on log-in for chats this browser remembers). The guest's email is
  only used to send them the link and reply alerts, never shown to the owner.
- Owners can't save (like) their own listings; they see a read-only saves count instead.
- CSP stays strict site-wide; only `/admin/` adds `'unsafe-eval'` (scripts) and `'unsafe-inline'`
  (styles), because django-unfold ships the standard Alpine build (`apps/core/csp.py`, user approved).
- `/s/<section>/` keeps its query string when redirecting to the campus/town section page.

## Known gaps / next steps
1. Admin review of the imported data: merge the remaining duplicate pairs (Catholic University
   is done), add a sourced point for NMTC Sunyani once Wikidata/OSM are corrected, verify campuses and areas; re-run areas for the 7 failed campuses;
   save the Ministry of Health PDF and (when GTEC fixes it) the accredited list into `data/raw/`.
2. Approve the OSM and Remotive sources in the admin after reading the terms, then `make import-external`.
3. Playwright smoke tests (M14) not written — `playwright` wheels for Python 3.15 were not checked.
4. Lighthouse mobile audit (M14) not run.
5. SMS provider adapters are stubs (out of scope per §12).
6. Raise coverage on `contacts`, `locations` and `notifications` services above 80% each.
7. Commits were grouped (not one per milestone) because the build happened in one pass.
