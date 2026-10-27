# KampusDey — Progress

## Status (2026-10-26): build in progress, NOT yet runnable end to end

Written so far (all milestones' code is drafted, none formally accepted):
- Foundation: settings split (`config/settings/{base,dev,test,prod}.py`), constance config, unfold sidebar, Celery + beat schedule, `.venv` with all deps, npm toolchain (Tailwind v4 + daisyUI 5, htmx, Alpine CSP, Leaflet, Inter) vendored via `npm run vendor`.
- Models + initial migrations for all 17 apps; `migrate` and `seed_locations` run (16 regions, 22 starter campuses, no coordinates).
- Services: accounts (permission rules, OTP, verification, deletion/export), locations (picker, GeoIP hint, importers for Wikidata/OSM/HDX/GTEC/MoH/Wikipedia, matching, merge, report), listings (wizard, snapping, auto-link, lifecycle, ranking, search), contacts (channel registry), boosts, engagement, chat, moderation rules engine, telemetry (buffer/flush/roll-ups), notifications, hostels, growth, external (source registry, OSM places, Remotive, claims).
- Views, URLs, admin (unfold) for every app; cotton components; most page templates.

## Left to do (next session)
1. Remaining templates: `external/` (around, place, claim, edit_place, partials/place_card), `growth/rent_check.html`, `pages/` (about, data_sources, safety, privacy, terms, offline, scam_alerts, `sw.js`), `errors/` (simple, 500), `partials/toast.html`, `emails/` (notifications/digest txt+html), admin templates (`admin/index.html` dashboard, locations review_queue/duplicates, sitesettings matrix + integration_change_form).
2. PWA icons `static/img/icon-192.png` / `icon-512.png`; `npm run build:css`.
3. Run `manage.py check`, `runserver`, fix errors; `seed_demo` command.
4. Tests (factories for every model, `tests/fixtures/sources/` recorded responses, key behaviours in §9), `ruff check`/`format`.
5. Makefile + `make.ps1`, `.env.example`, README, ARCHITECTURE/OPERATIONS/DATA_SOURCES docs, Dockerfile/compose (kept for later), CI.
6. git init done; nothing committed yet.

## Decisions
- **No Docker locally** (user request): Python venv + pip (`requirements*.txt`) instead of uv; SQLite default DB, PostgreSQL via `DATABASE_URL`.
- **No PostGIS/GDAL on this machine**: points stored as `lat`/`lng` floats; distances via haversine/SQL math (`apps/core/geo.py`); region boundaries as GeoJSON with pure-Python point-in-polygon.
- **No Redis required**: DB cache backend; Celery runs eager without a broker; `manage.py run_periodic [--loop]` replaces beat; telemetry buffer falls back to a `PendingEvent` table.
- Full-text search uses PostgreSQL `SearchVector` when on Postgres, `icontains` on SQLite. Trigram similarity and pHash implemented in Python (no pg_trgm / imagehash dependency).
- Notifications implemented in-house instead of django-notifications-hq.
- Tailwind built with npm `@tailwindcss/cli` + `daisyui` (allowed fallback in §3).
- Integration secrets cached only in-process (never in the shared cache) so they stay encrypted at rest; auditlog excludes secret fields and remote addresses.
