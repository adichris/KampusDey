# KampusDey

*Whatever you need on campus, e dey.*

KampusDey is a free, mobile-first web platform for students at universities and colleges across
Ghana. Students find hostels, rooms and roommates, buy and sell, and discover jobs, services, food,
events and study materials near their campus, then contact each other directly (WhatsApp, phone,
Telegram, email relay, in-app chat).

Django 6 · server-rendered templates · django-cotton · HTMX · Alpine (CSP build) · Tailwind v4 +
daisyUI 5 · Leaflet + OpenStreetMap.

## Quick start (local, no Docker)

Requirements: Python 3.12+ and Node 20+. PostgreSQL and Redis are optional.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Windows (Linux/macOS: .venv/bin/pip)
npm install
npm run vendor
npm run build:css
cp .env.example .env                                  # then set FIELD_ENCRYPTION_KEY
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createcachetable
.venv/Scripts/python manage.py seed_locations
.venv/Scripts/python manage.py seed_demo              # optional FAKE data, DEBUG only
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

Open <http://localhost:8000>. The admin is at `/admin/` (or `ADMIN_URL`). Staff must set up TOTP
on first visit; set `STAFF_MFA_REQUIRED=False` in `.env` for purely local work.

Windows has no `make`; every Makefile target also exists in PowerShell: `.\make.ps1 test`.

| Task | Command |
|---|---|
| Run tests | `make test` / `.\make.ps1 test` |
| Lint / format | `make lint`, `make fmt` |
| Build CSS (once / watch) | `make tailwind`, `make tailwind-watch` |
| Seed regions + starter campuses | `make seed` |
| Import real location data (internet) | `make import-locations` |
| Import places + remote jobs (internet, sources approved in admin) | `make import-external` |
| Run scheduled jobs without Celery beat | `make periodic` |

## Running without Docker, PostGIS or Redis

* **Database**: SQLite by default; set `DATABASE_URL=postgres://…` for PostgreSQL (full-text search
  with `SearchVector` is used automatically there).
* **Geo**: points are `lat`/`lng` floats; distances use the haversine formula in SQL
  (`apps/core/geo.py`). No GDAL needed.
* **Background jobs**: without `REDIS_URL`, Celery tasks run inline and `manage.py run_periodic
  --loop` runs the beat schedule. With Redis, run `celery -A config worker` and
  `celery -A config beat`.

## Documentation

* `docs/BUILD_PROMPT.md` — product and build specification (source of truth)
* `docs/DATA_SOURCES_PROMPT.md` — data sources and import pipelines
* `docs/PROGRESS.md` — milestone status, decisions, known gaps
* `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/DATA_SOURCES.md`

## Ground rules

No payment code. No secrets in the repository. No invented real-world data — location data and
external content come only from the approved sources, with provenance on every record.
