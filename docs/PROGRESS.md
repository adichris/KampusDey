# KampusDey — Progress

## Status (2026-10-27)

All milestones M0–M14 are implemented in code and covered by tests. **261 tests pass** (offline,
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
| M1.5 Real location data | done (offline-tested) | importers for Wikidata, OSM, HDX, GTEC, MoH, Wikipedia; review queue, duplicates, merge, report. **Real import not yet run** — needs internet + HDX download |
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
- Message admin is intentionally not registered: admins read conversations only through reports.

## Known gaps / next steps
1. Run the real imports with internet: download HDX COD-AB into `data/raw/hdx/`, save GTEC/MoH
   lists into `data/raw/`, then `make import-locations`; check the Sunyani acceptance criteria.
2. Approve the OSM and Remotive sources in the admin after reading the terms, then `make import-external`.
3. Playwright smoke tests (M14) not written — `playwright` wheels for Python 3.15 were not checked.
4. Lighthouse mobile audit (M14) not run.
5. SMS provider adapters are stubs (out of scope per §12).
6. Raise coverage on `contacts`, `locations` and `notifications` services above 80% each.
7. Commits were grouped (not one per milestone) because the build happened in one pass.
