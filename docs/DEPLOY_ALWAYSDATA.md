# Deploying KampusDey on alwaysdata

This guide runs KampusDey on an alwaysdata account with uploads kept on the account's own disk
(no S3 needed). Menu names follow the alwaysdata admin panel; if one looks different, check
alwaysdata's own documentation for "Python WSGI sites".

## Staging first

Run a staging copy before production, ideally on its own alwaysdata account (or at least its own
site, database and folders). Add `SITE_ENVIRONMENT=staging` to its `.env`: staging then
disallows all crawlers (`robots.txt` and `X-Robots-Tag`), shows a yellow "Staging site" bar,
prefixes account emails with `[KampusDey staging]` and reports to Sentry as `staging`.

Updating any copy later is one command over SSH, then a site restart:

```bash
cd ~/kampusdey && scripts/deploy.sh main
```

It pulls the branch, installs Python and npm packages, builds the CSS and vendored JS (they are
not in git), migrates, collects static files and runs `check --deploy`. Node.js must be
available on the account (alwaysdata: Environment → Node.js, any current LTS).

## 1. Folders

Keep code and uploads apart so a redeploy never touches user files:

```
/home/<account>/kampusdey/            ← the git checkout
/home/<account>/kampusdey/.venv/      ← virtualenv
/home/<account>/kampusdey-data/media/          ← public uploads (photos, PDFs)
/home/<account>/kampusdey-data/private_media/  ← ID documents, claim proofs (never public)
```

Over SSH:

```bash
git clone <repo-url> ~/kampusdey && cd ~/kampusdey
mkdir -p ~/kampusdey-data/media ~/kampusdey-data/private_media
```

## 2. Database

Create a PostgreSQL database and user under **Databases → PostgreSQL** and note the host
(e.g. `postgresql-<account>.alwaysdata.net`).

## 3. Environment (`~/kampusdey/.env`)

Only the values that must exist before the app starts live here. Everything else (email,
storage, Google sign-in, Turnstile, SMS, marketplace rules) is set later in the admin.

```
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<long random string>
FIELD_ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
DJANGO_ALLOWED_HOSTS=<account>.alwaysdata.net,kampusdey.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://<account>.alwaysdata.net,https://kampusdey.example
SITE_URL=https://kampusdey.example
ADMIN_URL=<something-hard-to-guess>/
DATABASE_URL=postgres://<user>:<password>@postgresql-<account>.alwaysdata.net:5432/<db>
MEDIA_ROOT=/home/<account>/kampusdey-data/media
PRIVATE_MEDIA_ROOT=/home/<account>/kampusdey-data/private_media
STORAGE_BACKEND=auto
SERVE_MEDIA=True
```

Keep a copy of `FIELD_ENCRYPTION_KEY` somewhere safe: without it the secrets saved in the
admin cannot be read.

Then (the deploy script creates the virtualenv, builds assets, migrates and collects static):

```bash
cd ~/kampusdey && scripts/deploy.sh main
. .venv/bin/activate
python manage.py seed_locations
python manage.py createsuperuser
```

## 4. The site

**Web → Sites → Add a site**, type **Python WSGI**:

- Application path: `/home/<account>/kampusdey/config/wsgi.py`
- Working directory: `/home/<account>/kampusdey`
- Virtualenv directory: `/home/<account>/kampusdey/.venv`
- Environment: `DJANGO_SETTINGS_MODULE=config.settings.prod` (the rest is read from `.env`)

Static files (CSS/JS) are served by WhiteNoise, so nothing else is needed for them.

### Serving uploads

With no S3 bucket configured, uploads are written to `MEDIA_ROOT` and Django serves them at
`/media/…` with long cache headers and a locked-down security policy. That works as-is.

For better speed, let alwaysdata's web server serve them directly: if the site form offers a
static-files mapping, map `/media/` to `/home/<account>/kampusdey-data/media/` and set
`SERVE_MEDIA=False`. Never map `private_media`.

## 5. Background jobs

Without Redis, tasks run inline and the periodic jobs (expiry, digests, roll-ups) run from a
scheduled task. Under **Advanced → Scheduled tasks**, add an hourly command:

```
cd /home/<account>/kampusdey && .venv/bin/python manage.py run_periodic
```

## 6. Finish in the admin

Open `https://<your-site>/<ADMIN_URL>overview/` (Settings → Settings overview). It shows what
is active and links to each place to change it:

- **Integrations → Email (SMTP)**: alwaysdata's SMTP (`smtp-<account>.alwaysdata.net`,
  port 587, STARTTLS, your mailbox login), then press **Send test email**.
- **Integrations → File storage**: leave empty to keep uploads on the server. To move to
  S3/Cloudflare R2 later, copy `~/kampusdey-data/media/` into the bucket first, then fill
  in the bucket fields.
- **Integrations → Google sign-in, Turnstile, SMS, GeoLite2, Umami** as needed.
- **Site settings**: marketplace rules (expiry, boosts, guest chat limit, themes, map tiles).

## 7. Error tracking (Sentry)

Add the project's DSN to `.env` and restart the site:

```
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

Events are tagged with `SITE_ENVIRONMENT` (staging/production) and the deployed git commit as
the release. No IP addresses, cookies, request bodies, local variables or contact details are
sent. Check that events arrive:

```bash
cd ~/kampusdey && .venv/bin/python manage.py sentry_check
```

## 8. Backups

Back up the database (alwaysdata keeps daily database backups) **and**
`~/kampusdey-data/`, which holds every uploaded photo and document.
