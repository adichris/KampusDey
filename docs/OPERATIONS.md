# Operations

## Environment
All variables are documented in `.env.example`. Production uses `config.settings.prod`
(HSTS, secure cookies, SSL redirect). Required in production: `DJANGO_SECRET_KEY`,
`FIELD_ENCRYPTION_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `SITE_URL`, SMTP settings.
Run `manage.py check --deploy` before each release.

Processes:
```
gunicorn config.wsgi --workers 3
celery -A config worker -l info
celery -A config beat -l info
```
Without Redis, replace the two Celery processes with `manage.py run_periodic --loop`.

## Backups
PostgreSQL: nightly `pg_dump -Fc "$DATABASE_URL" > kampusdey-$(date +%F).dump`, keep 14 daily and
8 weekly copies off-site. Media lives in object storage (enable bucket versioning). The private
bucket (verification documents, claim proofs) holds only files awaiting review.

## Admin-editable settings
Everything in §6.14 of the build prompt is under **Settings → Site settings** (constance), grouped
by Lifecycle, Boosts, Ranking, Maps, Trust, Appearance, Telemetry and External content. Section
switches per campus: **Settings → Section availability → matrix**.

## Integrations (superadmin only)
**Settings → Integrations** stores SMS, Turnstile, GeoLite2 and Umami settings. Secret fields are
Fernet-encrypted and never shown again (the form shows "•••• set"). Buttons on that page: *Send test
email*, *Send test SMS*, *Update GeoLite2 now*.

### Key rotation
Prepend a new key to `FIELD_ENCRYPTION_KEY` (`new,old`), deploy, run `manage.py rotate_field_keys`,
then remove the old key.

## GeoLite2
Create a free MaxMind account, enter the account ID and licence key in Integrations, then click
*Update GeoLite2 now* (or wait for the weekly task). The database is saved in `GEOIP_PATH` and only
pre-highlights a region in the picker. Missing database = no hint, no errors.

## Switching the tile provider
Change `MAP_TILE_URL` and `MAP_ATTRIBUTION` in Site settings. The OSM Foundation tile servers are for
light use only; for real traffic use a commercial or self-hosted provider and keep its attribution.
Tiles are never pre-fetched or cached by the service worker. Image CSP already allows `https:`.

## Enabling phone verification
1. Choose an SMS provider in Integrations (`console` prints codes to the server log for testing).
   Production adapters (Hubtel, Arkesel, mNotify) are interface stubs and must be implemented first.
2. Use *Send test SMS*.
3. Tick **Require phone verification**. Users are prompted at their next login and cannot chat or
   boost until verified.

## Email DNS (SPF, DKIM, DMARC)
For the sending domain:
* SPF: `TXT @ "v=spf1 include:<provider-spf> -all"`
* DKIM: publish the provider's selector record, e.g. `TXT s1._domainkey "<provider value>"`
* DMARC: `TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; adkim=s; aspf=s"`
Start DMARC with `p=none` for two weeks, review reports, then move to `quarantine`.

## Data protection checklist
* No raw IPs in application tables (telemetry hashes sessions; auditlog remote address disabled).
  django-axes keeps login attempts for 30 days for lockouts, then purges them daily.
* EXIF stripped from all uploads; verification documents and claim proofs deleted after decisions.
* Approximate locations for rooms, roommates, food and lost & found; pins snapped to 200 m.
* Phone numbers never in initial HTML.
* Users can export (JSON) and delete their accounts from Profile.
* Raw telemetry deleted after `TELEMETRY_RAW_RETENTION_DAYS` (90).

## Imports
See `docs/DATA_SOURCES.md`. `make import-locations` and `make import-external` need internet.
