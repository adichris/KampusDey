# AGENTS.md — KampusDey

Instructions for coding agents working in this repository.

## Read first
1. `docs/BUILD_PROMPT.md`: the full product and build specification. It is the source of truth.
2. `docs/DATA_SOURCES_PROMPT.md`: real data sources and import pipelines: location data (Milestone M1.5) and external content, i.e. places around campus and remote jobs (Milestone M9.5).
3. `docs/PROGRESS.md`: which milestones are done, decisions made, known gaps. Continue from the first unfinished milestone.

## Commands
- `make up` / `make down`: start or stop the Docker Compose stack (web, worker, beat, db, redis, mailpit).
- `make migrate`: run migrations. `make makemigrations`: create them.
- `make test`: run pytest (inside Docker). `make test-fast` for a quick subset if defined.
- `make lint` (`ruff check`) and `make fmt` (`ruff format`).
- `make tailwind`: build CSS once. `make tailwind-watch` in development.
- `make seed`: seed regions and starter campuses. `make import-locations`: import real location data; `make import-external`: import places and remote jobs from approved sources (both need internet). `make seed-demo`: fake demo data, dev only.
Keep these targets working whenever you change tooling.

## Rules
- Work one milestone at a time. Finish it only when its acceptance criteria pass, tests are green, lint is clean, migrations are committed and `docs/PROGRESS.md` is updated.
- Business logic lives in each app's `services.py` / `selectors.py`; views stay thin; Celery tasks are idempotent.
- Server-rendered Django templates + django-cotton components + HTMX. Alpine.js only for small client state. No SPA frameworks.
- Use daisyUI semantic colour classes only (`bg-base-100`, `btn-primary`, …). Never hard-code colours; every page must work in every offered theme.
- Mobile-first: test layouts at 360px width.
- Wrap user-facing strings for translation.
- Never add payment code. `Boost.source` stays `free`.
- Never commit secrets. New settings go in `.env.example` (env) or constance (admin-editable), as the build prompt specifies.
- Never seed invented real-world data (coordinates, phone numbers, businesses). Real location data only from the sources in `docs/DATA_SOURCES_PROMPT.md`, with provenance on every record. Never scrape listings or personal details from other platforms. Demo data only through `seed_demo`, which refuses to run when `DEBUG=False`.
- External content comes only from sources approved in the Source registry; it is always labelled with its source and attribution, kept out of ranking and boosts, and external jobs never get JobPosting data or go into sitemaps, emails or alerts.
- Tests never call the network; use the recorded responses in `tests/fixtures/sources/`.
- Privacy: no raw IP addresses in application tables; strip EXIF from uploads; contact numbers never in initial HTML; approximate locations for rooms, roommates, food and lost & found.
- Maps: OpenStreetMap tiles via the configurable `MAP_TILE_URL`; always show attribution; never cache or pre-fetch tiles.
- Every new model gets admin registration, a factory and tests.

## Commits
- Small, focused commits with messages prefixed by milestone, e.g. `M3: add photo pipeline with EXIF stripping`.
- Run `make lint` and `make test` before committing.

## When unsure
Choose the simplest robust option that fits the build prompt, implement it, and record the decision in `docs/PROGRESS.md`.
