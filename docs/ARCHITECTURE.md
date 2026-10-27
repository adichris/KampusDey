# Architecture

## Layers
* **Views** (`apps/*/views.py`) are thin: parse the request, call a service or selector, render.
* **Services** (`services.py`) hold business rules and writes; **selectors** (`selectors.py`) hold
  read queries. Celery tasks (`tasks.py`) only call services and are idempotent.
* **Templates** are server-rendered. Reusable UI lives in `templates/cotton/` (django-cotton).
  HTMX handles partial updates (likes, comments, chat polling, infinite scroll, steppers,
  phone reveal). Alpine (CSP build) is loaded for small client state; most behaviour is in
  `static/js/app.js` using `data-*` attributes so no inline JavaScript is needed.

## Apps
| App | Responsibility |
|---|---|
| core | base models, geo/text/image helpers, template tags, `run_periodic`, `seed_demo` |
| accounts | custom `User` (email login), `Profile`, permission rules, phone OTP, SMS backends, verification, deletion/export |
| locations | regions, districts, towns, institutions, campuses, areas, provenance, picker, GeoIP hint, import pipeline |
| listings | `Listing`, section registry (`sections.py`), 17 details models, wizard, ranking, lifecycle, search |
| contacts | contact cards/channels and the channel handler registry |
| boosts | free boosts with limits (`source` is always `free`) |
| engagement | likes, comments (masked), reviews, reports, saved searches, shares |
| chat | conversations under aliases, messages, blocks |
| moderation | rules engine, moderation queue, banned terms, scam alerts, price suggestions |
| telemetry | event buffer + flush, dedupe, roll-ups, retention |
| notifications | in-app, batched email, web push, preferences |
| hostels | Hostel Manager; room types own `rooms` listings |
| growth | referrals, digest, rent check, spotlight, sitemaps |
| external | source registry, OSM places + claims, Remotive jobs, partner feeds |
| sitesettings | encrypted `IntegrationSettings`, `SectionAvailability` |
| dashboard | poster dashboard, unfold admin dashboard callback |
| pages | static pages, manifest, service worker, robots |

## Key flows
* **Location context**: `CampusContextMiddleware` sets `request.location` from the profile or a
  signed cookie; the context processor exposes `current_campus` / `current_town`.
* **Posting**: picker → draft → step 1 photos (EXIF stripped, re-encoded, pHash) → step 2 details
  + map pin (snapped to `LOCATION_SNAP_M`) → step 3 contact + campus links → `publish()` runs the
  rules engine and sends new sellers' posts to review.
* **Contact**: buttons come from the channel registry; phone numbers are only returned by the
  HTMX tap endpoint after a tap is logged.
* **Telemetry**: `record()` dedupes views per hashed session/day in the cache and pushes to Redis
  or the `PendingEvent` table; `flush` bulk-creates `Event` rows every minute.

## Data and geo
Points are stored as `lat`/`lng`. `apps/core/geo.py` provides bounding-box pre-filtering plus an
exact distance expression that works on SQLite and PostgreSQL. Region boundaries are GeoJSON with
a pure-Python point-in-polygon. Moving to PostGIS later means adding `PointField`s and replacing
`geo.nearby()`; callers do not change.
