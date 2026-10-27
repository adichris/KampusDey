# KampusDey — Master Build Prompt for Codex

> **How to use this file**
> 1. Create an empty Git repository and commit this file as `docs/BUILD_PROMPT.md`, the data prompt as `docs/DATA_SOURCES_PROMPT.md`, and `AGENTS.md` at the repo root.
> 2. Start Codex with: **"Read AGENTS.md and docs/BUILD_PROMPT.md. Build Milestone 0, then stop and report."**
> 3. For every later session: **"Continue with the next unfinished milestone in docs/BUILD_PROMPT.md. Check docs/PROGRESS.md first."**
>
> Work one milestone at a time. Do not start the next milestone until the current one meets every acceptance criterion.

---

## 1. Mission

Build **KampusDey** (tagline: *"Whatever you need on campus, e dey."*), a location-based web platform for university and college students across Ghana. Students find hostels, rooms and roommates, buy and sell items, and discover jobs, services, food, events and study materials near their campus. Users contact each other directly (WhatsApp, phone, Telegram, email relay, in-app chat).

The product must be:

- **Free at launch.** No payment code at all.
- **Complete at launch.** All 18 sections ship together on one shared core.
- **Mobile-first, fast and clean.** Most users are on Android phones with mobile data.
- **Configurable without code.** Limits, integrations, themes and feature switches live in the admin.

---

## 2. Ground rules (non-negotiable)

1. **Milestone order.** Build milestones in order. Each ends with: all tests passing, `ruff check` and `ruff format --check` clean, migrations committed, `docs/PROGRESS.md` updated (what was done, decisions made, known gaps).
2. **No payments.** Do not add Paystack or any payment code. The `Boost.source` field exists with choices `free`/`paid`; only `free` is used now.
3. **No secrets in code.** Read secrets from environment variables (`django-environ`). Keep `.env.example` complete and commented. Third-party keys entered in the admin are stored **encrypted** (see §8.3).
4. **No invented real-world data.** Never seed fake coordinates, phone numbers, businesses, people or listings. Real location data and external content (places around campus, remote jobs) come only from the sources and admin-approved Source registry in `docs/DATA_SOURCES_PROMPT.md`, with provenance on every record (Milestones M1.5 and M9.5). Never scrape listings or personal details from other platforms. Demo data lives only in a separate `seed_demo` command clearly marked as fake and refused when `DEBUG=False`.
5. **Server-rendered first.** Django templates + django-cotton components + HTMX. Alpine.js only for small client-side state. No SPA framework.
6. **Thin views, services for logic.** Business rules live in `services.py` / `selectors.py` per app. Celery tasks must be idempotent.
7. **Mobile-first.** Every page must work at 360px width with no horizontal scroll.
8. **i18n-ready.** Wrap user-facing strings with `gettext`/`{% translate %}`. English only for now.
9. **Privacy by default.** No raw IP addresses in application tables (telemetry uses hashed sessions). Strip EXIF from uploads. Approximate locations for sensitive posts.
10. **Ask nothing, decide sensibly.** When something is unspecified, choose the simplest robust option, implement it, and record the decision in `docs/PROGRESS.md`.

---

## 3. Tech stack

| Area | Choice |
|---|---|
| Language / framework | Python 3.12+, **Django 6 LTS** |
| Dependencies | `uv` with `pyproject.toml` + `uv.lock` |
| Database | PostgreSQL 16 + **PostGIS** (GeoDjango) |
| Cache / broker | Redis |
| Background jobs | Celery + django-celery-beat |
| Accounts | **django-allauth** (email login, mandatory email verification, optional Google login, MFA for staff), django-phonenumber-field |
| Settings in admin | **django-constance** (database backend) |
| Feature flags | django-waffle (global flags) + own `SectionAvailability` model (per campus) |
| Admin | **django-unfold** |
| Frontend | **Tailwind CSS v4 + daisyUI 5**, **django-cotton** components, **django-htmx**, Alpine.js (CSP build), Lucide icons |
| Maps | **Leaflet + OpenStreetMap tiles**, GeoDjango, PostGIS |
| IP hint | MaxMind **GeoLite2** City via `django.contrib.gis.geoip2` |
| Search / filters | PostgreSQL full-text search (`SearchVectorField` + GIN), django-filter, django-taggit |
| Images | django-imagekit (WebP renditions), Pillow, `imagehash` (perceptual hash), django-cleanup |
| Storage | django-storages (S3-compatible, e.g. Cloudflare R2) in production; local in dev. Separate **private** storage for verification documents |
| Notifications | django-notifications-hq, django-webpush, SMTP email |
| Safety | django-ratelimit, django-axes, Cloudflare Turnstile (server-side verification), django-auditlog, django-csp |
| SEO | Django sitemaps, django-meta, JSON-LD |
| Static files | WhiteNoise |
| Monitoring | Sentry SDK; django-debug-toolbar in dev |
| Tests / quality | pytest, pytest-django, factory_boy, coverage, ruff, pre-commit, GitHub Actions |
| Dev email | Mailpit (Docker) |
| Optional analytics | Self-hosted Umami (Docker Compose profile `analytics`) |

**Tailwind build:** prefer `django-tailwind-cli` (standalone Tailwind v4 binary, no Node). Load daisyUI 5 using its standalone plugin files. If that proves unworkable, use a minimal `package.json` with `tailwindcss`, `@tailwindcss/cli` and `daisyui`, and document the choice.

**Docker Compose services (dev):** `web`, `worker`, `beat`, `db` (PostGIS image), `redis`, `mailpit`; optional profile `analytics` with `umami` + its database.

---

## 4. Repository layout

```
kampusdey/
├── AGENTS.md
├── README.md
├── Makefile                 # up, down, migrate, test, lint, fmt, tailwind, shell, seed
├── pyproject.toml / uv.lock
├── Dockerfile / docker-compose.yml / .env.example
├── config/
│   ├── settings/{base,dev,test,prod}.py
│   ├── urls.py  celery.py  asgi.py  wsgi.py
├── apps/
│   ├── core/          # TimeStampedModel, utils, context processors, templatetags (ghs, timesince), theme
│   ├── accounts/      # custom User, Profile, onboarding, badges, VerificationRequest, phone OTP, sms backends
│   ├── locations/     # Region, Town, Campus, Area, CampusRequest, picker, GeoIP hint
│   ├── listings/      # Listing, details models, categories, photos, wizard, detail/section views, search, ranking, lifecycle
│   ├── hostels/       # Hostel, HostelRoomType, Hostel Manager dashboard
│   ├── contacts/      # ContactCard, ContactChannel, channel handler registry, email relay
│   ├── boosts/
│   ├── engagement/    # Like, Comment, Review, Report, SavedSearch
│   ├── chat/          # Conversation, Message, Block
│   ├── moderation/    # ModerationItem, BannedTerm, rules engine, ScamAlert
│   ├── telemetry/     # Event, DailyListingStats, DailyCampusStats, buffer + flush, roll-ups
│   ├── notifications/ # preferences, email + webpush dispatch
│   ├── growth/        # Referral, ambassadors, digest, rent check, spotlight, search gaps
│   ├── external/      # Source registry, Place (OSM, claimable), ExternalJob (Remotive), importers (M9.5)
│   ├── sitesettings/  # IntegrationSettings (singleton, encrypted), SectionAvailability, constance config
│   ├── dashboard/     # poster dashboard, admin analytics (unfold dashboard callback)
│   └── pages/         # home, about, safety tips, privacy, terms, offline page
├── templates/
│   ├── base.html  layouts/  partials/
│   └── cotton/        # reusable components (§7.3)
├── static/
│   ├── src/styles.css # Tailwind + daisyUI entry
│   └── js/            # theme.js, map.js, small helpers
├── fixtures/          # regions.json, campuses_seed.json (names only)
└── docs/
    ├── BUILD_PROMPT.md  PROGRESS.md  ARCHITECTURE.md  OPERATIONS.md
```

Use a **custom User model from the first migration**.

---

## 5. Domain model

Field lists are the minimum; add timestamps (`created_at`, `updated_at`) via `TimeStampedModel` everywhere. Add sensible indexes, `__str__`, admin registration and factories for every model.

### 5.1 accounts

- **User** (`AbstractUser`): `email` (unique, login), `display_name`, `phone` (PhoneNumberField, null, unique when set), `phone_verified` (bool), `theme` (char, default `system`), `alias_number` (int, random 4 digits, used for anonymous aliases).
- **Profile** (1:1 User): `role` [student, landlord, agent, vendor, employer, other], `seller_type` [student, business] (nullable), `home_campus` (FK Campus, null), `home_town` (FK Town, null), `followed_campuses` (M2M Campus), `level` (optional), `bio`, `avatar`, `is_ambassador`, badge booleans `verified_student`, `verified_landlord`, `verified_agent` with `*_at` timestamps.
- **VerificationRequest**: `user`, `kind` [student, landlord, agent], `document` (FileField on **private** storage), `status` [pending, approved, rejected], `reviewed_by`, `reviewed_at`, `note`. On approve/reject: set badge, then **delete the document file** and keep only the result.
- **PhoneOTP**: `user`, `phone`, `code_hash`, `expires_at`, `attempts`, `used_at`. Own small flow (not allauth phone login) so it can be switched on at runtime.

### 5.2 locations

- **Region**: `name`, `slug`. Seed Ghana's 16 regions: Ahafo, Ashanti, Bono, Bono East, Central, Eastern, Greater Accra, North East, Northern, Oti, Savannah, Upper East, Upper West, Volta, Western, Western North.
- **Town**: `region`, `name`, `slug`, `point` (PointField geography, null).
- **Campus**: `town`, `name`, `short_name`, `slug`, `kind` [university, university_college, technical_university, college_of_education, nursing_midwifery, health_training, other], `point` (null), `is_active`. M1.5 adds an `Institution` parent model, provenance fields and region boundaries (see `docs/DATA_SOURCES_PROMPT.md`).
- **Area**: `town`, `campus` (null), `name`, `slug`, `boundary` (MultiPolygon, null), `point` (null).
- **CampusRequest**: `name`, `town_name`, `region`, `requester` (null), `email`, `status` [pending, added, rejected]; admin action "Approve and create campus".

### 5.3 listings

- **Listing**: `owner`, `section` (choices below), `title`, `slug`, `description`, `price` (Decimal, null), `price_period` [total, per_year, per_semester, per_month, per_night, per_hour], `negotiable`, `is_free`, `town` (FK), `area` (FK null), `campuses` (M2M through **ListingCampus**: `listing`, `campus`, `distance_m`, `is_manual`, `is_excluded`), `location` (PointField geography, **snapped**, null), `contact_card` (FK), `contact_visibility` [public, members], `status` [draft, pending_review, active, needs_check, expired, archived, taken], `published_at`, `confirmed_at`, `expires_at`, `score` (float, cached ranking), denormalised counters `views_7d`, `taps_7d`, `likes_count`, `comments_count`, `reports_count`, `search_vector` (SearchVectorField + GIN index).
- **Sections** (slug → details model):

| Section slug | Details model | Key fields |
|---|---|---|
| `rooms` | RoomDetails | room_type [single, 2_in_1, 3_in_1, 4_in_1, self_contained, chamber_hall], gender [male, female, mixed], rooms_per_meter, water_supply [flowing, tank, intermittent, none], washroom [in_room, shared], kitchen, wifi, security, furnished, mattress_included, available_from, hostel_room_type (FK null) |
| `roommates` | RoommateDetails | post_kind [have_room, need_room], gender_pref, budget_min, budget_max, level, move_in_date, habits (multi-choice: quiet, social, early_sleeper, late_sleeper, very_tidy, relaxed, non_smoker) |
| `short-stays` | ShortStayDetails | room_type, available_from, available_to |
| `buy-sell` | ItemDetails | category (FK ItemCategory), condition [new, like_new, used] |
| `wanted` | WantedDetails | category, budget_max, needed_by |
| `free-leaving` | ItemDetails | category, condition, pickup_by |
| `services` | ServiceDetails | service_type (FK ServiceCategory: laptop repair, phone repair, printing, hair, laundry, photography, tutoring, vacation storage, other), price_from, hours_text, area_served |
| `jobs` | JobDetails | job_type [part_time, internship, attachment, gig, full_time], pay_text, hours_text, deadline, how_to_apply, apply_url |
| `job-requests` | JobRequestDetails | skills (tags), availability, expected_pay |
| `errands` | ErrandDetails | deadline, pickup_area, dropoff_area |
| `food` | FoodDetails | post_kind [extra_food, need_food], pickup_from, available_until (≤ `FOOD_POST_MAX_HOURS`), food_note. **Price must be empty** |
| `events` | EventDetails | starts_at, ends_at, venue, organiser, ticket_info |
| `notes` | NoteDetails | course_code, course_title, level, format [file, physical, both], file (PDF only, size-limited, null) |
| `study` | StudyDetails | kind [study_partner, tutor], course_code, level, schedule_text, mode [online, in_person] |
| `lost-found` | LostFoundDetails | kind [lost, found], item_type, happened_at |
| `trips` | TripDetails | origin_town, destination_town, departs_at, seats_available, cost_share. Section **disabled by default** until legal check |
| `alerts` | AlertDetails | alert_type [water, power, security, venue_change, other], valid_until |
| `ask` | QuestionDetails | tags |

- **ItemCategory / ServiceCategory**: `name`, `slug`, `icon` (Lucide name), `min_price`, `max_price` (for moderation), `order`, `is_active`. Admin-managed. Seed: phones, laptops, tablets, mattresses & bedding, furniture, gas cylinders & kitchen, books & stationery, fashion, shoes, bags & accessories, beauty, electronics, sports, other.
- **ListingPhoto**: `listing`, `image`, `order`, `width`, `height`, `phash`. Renditions via imagekit: `thumb` 400w WebP, `card` 800w WebP, `full` 1600w WebP. Max photos `MAX_PHOTOS` (default 8), max upload `MAX_UPLOAD_MB` (default 8). **Strip all EXIF** (GPS) on upload. Verify images with Pillow; reject non-images.

### 5.4 hostels

- **Hostel**: `owner`, `name`, `slug`, `description`, `rules`, `amenities` (multi-choice), `town`, `campuses` (M2M), `location` (snapped), `contact_card`, `is_verified`.
- **HostelRoomType**: `hostel`, `name`, `room_type`, `gender`, `price`, `price_period`, `total_rooms`, `available_rooms`.
- **HostelPhoto**: same treatment as ListingPhoto.
- Each room type can generate/own a `rooms` Listing. When `available_rooms` hits 0, the listing becomes `taken`; when it rises above 0, it returns to `active`.

### 5.5 contacts

- **ContactCard**: `owner`, `label` ("Personal", "Hostel office"), `preferred_time`, `is_default`.
- **ContactChannel**: `card`, `kind` [whatsapp, phone, telegram, email, chat], `value`, `is_verified`, `order`.
- **Channel handler registry** (`contacts/channels.py`): each kind registers a handler with `is_available(listing, viewer)`, `render_button(listing, viewer)` and `action_url(listing, viewer)`. Adding a channel = one choice + one handler.
  - **WhatsApp:** `https://wa.me/<E.164 digits>?text=<urlencoded "Hi, I saw your listing on KampusDey: <title> <absolute url>">`.
  - **Phone:** "Show number" button → HTMX POST (logs a tap) → reveals number with `tel:` link. **Numbers are never present in the initial HTML.**
  - **Telegram:** `https://t.me/<username>`.
  - **Email relay:** form for verified users; sends the message to the owner via SMTP with the sender's verified email as `Reply-To` (disclosed on the form); rate-limited.
  - **Chat:** opens/creates a Conversation (§6.8).
- Visibility: if `contact_visibility = members` and the viewer is anonymous, show "Log in to contact this person" instead of buttons.

### 5.6 boosts

- **Boost**: `listing`, `user`, `source` [free, paid] (default free), `starts_at`, `ends_at`.
- `services.can_boost(user, listing)` checks: verified email (and verified phone if `require_phone_verification`), account age ≥ `BOOST_MIN_ACCOUNT_AGE_HOURS`, ≤ `BOOSTS_PER_WEEK` boosts in the rolling 7 days, listing `active`, no active boost on it.
- Boost ends automatically when the listing becomes `taken`, `expired` or `archived`.

### 5.7 engagement

- **Like**: `user`, `listing` (unique together). A like also appears in the user's **Saved** list.
- **Comment**: `listing`, `author`, `parent` (null, one level of replies), `body` (stored **masked**), `is_owner_reply`, `is_hidden`.
- **Review**: `reviewer`, `hostel` (null), `target_user` (null), `rating` 1–5, `body`, `status` [visible, hidden].
- **Report**: generic relation (`content_type`, `object_id`), `reporter`, `reason` [scam, fake_listing, wrong_price, offensive, spam, duplicate, other], `details`, `status` [open, actioned, dismissed], `handled_by`.
- **SavedSearch**: `user`, `params` (JSON of filters), `campus`, `section`, `last_notified_at`, `is_active`.

### 5.8 chat

- **Conversation**: `listing`, `starter`, `owner`, `starter_alias`, `owner_alias`, `last_message_at`, `is_blocked`. Unique (`listing`, `starter`).
- **Message**: `conversation`, `sender`, `body`, `kind` [text, shared_contact, system], `has_scam_warning`, `read_at`.
- **Block**: `blocker`, `blocked`.

### 5.9 moderation

- **BannedTerm**: `term`, `is_regex`, `action` [block, review, warn], `applies_to` [listing, comment, message, all].
- **ModerationItem**: generic relation, `reason`, `auto` (bool), `status` [pending, approved, rejected], `reviewed_by`.
- **ScamAlert**: `name`, `phone_last4` (only last 4 digits shown publicly), `description`, `evidence_note` (admin only), `confirmed_at`, `is_published`. Only admin-confirmed entries are published.

### 5.10 telemetry

- **Event**: `kind` [view, tap, like, unlike, share, search, boost], `listing` (null), `user` (null), `session_hash` (HMAC-SHA256 of session key + date with `SECRET_KEY`-derived salt), `campus` (null), `town` (null), `meta` (JSON: channel for taps, query + result count for searches), `created_at` (indexed). Composite indexes on (`kind`, `created_at`) and (`listing`, `created_at`).
- **DailyListingStats**: `listing`, `date`, `views`, `taps`, `likes`, `shares`, `comments` (unique `listing`+`date`).
- **DailyCampusStats**: `campus`, `date`, `signups`, `posts`, `views`, `taps`, `searches`, `zero_result_searches`.

### 5.11 growth

- **Referral**: `ambassador`, `referred_user`, `rewarded` (bool). Reward = extra free boosts (setting `AMBASSADOR_BONUS_BOOSTS`).
- **Spotlight**: `listing` or `user`, `week_start`, `blurb` ("Student Business of the Week").

### 5.12 sitesettings

- **IntegrationSettings** (singleton, superadmin-only in admin): `sms_provider` [none, console, hubtel, arkesel, mnotify, other], `sms_api_key`*, `sms_api_secret`*, `sms_sender_id`, `require_phone_verification` (bool, default False), `turnstile_site_key`, `turnstile_secret`*, `geolite2_account_id`, `geolite2_license_key`*, `geolite2_last_updated`, `umami_script_url`, `umami_website_id`. Fields marked * are **encrypted at rest** with Fernet (`cryptography`), key from env `FIELD_ENCRYPTION_KEY`. Implement a small `EncryptedTextField`; never display decrypted secrets in the admin (show "•••• set" with a replace field).
- **SectionAvailability**: `section`, `campus` (null = global default), `enabled`. Resolution: campus row → global row → default (all on, except `trips` off).
- **SMTP** credentials come from environment variables only; the admin shows status and a "Send test email" action.

---

## 6. Feature requirements

### 6.1 Location picker and campus context

- On first visit (no location cookie/profile value), show a **"Where are you?"** bottom sheet with: (1) search over campuses grouped by region; (2) "Use my current location" (browser Geolocation API with permission → nearest 5 campuses via PostGIS); (3) "Other (not on a campus)" → choose region then town; (4) "My school isn't listed" → CampusRequest form.
- **GeoIP hint only:** if a GeoLite2 database is present, pre-highlight the matching region in the picker ("Looks like you're in Bono"). Never auto-select. Never use IP for nearby or ranking. Gracefully skip if the database is missing.
- Store the choice in a signed cookie for guests and on Profile for users. A **campus switcher** in the header changes it anytime. Users can follow several campuses.
- A request context processor exposes `current_campus` / `current_town` to all templates.
- Management command `update_geolite2` downloads the database using the stored account ID + licence key; Celery beat runs it weekly.

### 6.2 Accounts, onboarding and verification

- allauth: email as username, `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, verification by code or link, password reset by email, optional Google provider configured from env, **MFA (TOTP) required for staff**.
- Turnstile on sign-up, login and posting forms when keys are set (server-side verification).
- Onboarding after first login: role, location (reuse picker), seller type if vendor, display name.
- Permission helpers in `accounts/services.py`: `can_post`, `can_comment`, `can_like`, `can_chat`, `can_message_first_time`, `can_boost`. **Interim rules** while phone verification is off: verified email required; account ≥ `FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS` (24) to message someone new or boost; new accounts limited to `CHAT_NEW_ACCOUNT_DAILY_LIMIT` messages/day for `CHAT_NEW_ACCOUNT_DAYS` days.
- **Phone OTP** (runtime switch): when `require_phone_verification` is on, users without a verified phone are prompted at next login and blocked from boosting/chat until verified. OTP: 6 digits, hashed, 10-minute expiry, 3 attempts, resend after 60s, rate-limited per user and IP. SMS sending through an `SMSBackend` interface (`send(to, message)`) with a `ConsoleSMSBackend` (logs) and provider adapter stubs selected by `sms_provider`. A "Send test SMS" admin action.
- Verification requests with private file storage and automatic deletion after decision.
- **Account deletion** (anonymise listings/messages, remove personal data) and **data export** (JSON download of the user's profile, listings and messages).

### 6.3 Post wizard and listing pages

- "+ Post" → pick section → **3-step HTMX wizard**: (1) photos (drag/drop, reorder, client-side resize before upload where possible); (2) details (section-specific form + common fields + map pin with Leaflet; location is snapped to `LOCATION_SNAP_M` grid on save); (3) contact & visibility (pick contact card, channels, visibility, preferred time, hide-number option) and campus links (auto-linked campuses within `CAMPUS_AUTOLINK_RADIUS_M`, user can untick or add).
- Drafts auto-save on each step.
- **Listing page:** photo carousel, key facts as chips, description, approximate map (circle, not a pin), Q&A comments, like/share/report, related listings, **sticky contact bar** (WhatsApp · Call · Chat, depending on channels).
- **Card info line per section:** rooms → price per period + room type; jobs → pay + type; events → date/time + venue; food → available until; trips → route + departure; etc.
- **Food rules:** `need_food` posts are members-only, show only the alias, never appear in public feeds for guests; `extra_food` posts expire at `available_until`; every food post shows a food-safety note; price is disallowed.

### 6.4 Discovery

- **Home:** campus switcher + search; horizontal section chips (only enabled sections); feeds "Near you", "Boosted", "New today"; friendly empty states with a "Post the first one" button.
- **Section pages** `/<campus-slug>/<section-slug>/` and `/town/<town-slug>/<section-slug>/`: django-filter filters per section, sorts **Recommended / Newest / Price / Distance**, list ⇄ map toggle, infinite scroll via HTMX.
- **Search:** full-text across sections within the current campus/town, with section facets. Log every search as a telemetry `search` event including result count.
- **Ranking** (periodic task every 15 min writes `Listing.score`):
  `score = W_FRESH * exp(-age_days / FRESH_HALF_LIFE_DAYS) + W_ACT * min(log1p(3*taps_7d + 2*likes_7d + 0.2*views_7d), ACTIVITY_CAP) + W_QUAL * (has_3_photos + owner_verified) − W_REPORT * reports_count`. All weights in constance.
- **Boosted slots:** top `BOOST_SLOTS_PER_PAGE` (default 4) on feeds and section pages, randomly rotated (seed per 10-minute window), labelled "Boosted", never more than that per page.

### 6.5 Maps and nearby

- Leaflet everywhere maps appear. Tile URL and attribution come from constance (`MAP_TILE_URL`, `MAP_ATTRIBUTION`). Always display attribution. Do not set a restrictive `Referrer-Policy` on map pages (use `strict-origin-when-cross-origin`). **Never pre-fetch, bulk-download or service-worker-cache tiles.**
- **Nearby** page: full-screen map, section filter chips, radius rings from `NEARBY_RADII` (default 500, 1000, 2000 m), uses browser geolocation or falls back to the chosen campus/town point.
- Distances computed in PostGIS; show **walking minutes** = ceil(distance_m / `WALKING_M_PER_MIN`).
- Sensitive sections (rooms, roommates, food, lost-found) render an approximate circle, never an exact pin. Exact addresses are only shared by the owner in chat.
- No geocoding-as-you-type. If address lookup is ever added, call Nominatim at most once per second, server-side, with caching and a proper User-Agent.

### 6.6 Lifecycle

Celery beat tasks:
- **New listings** from accounts with fewer than `NEW_SELLER_REVIEW_COUNT` (3) approved posts → `pending_review`.
- **Day 14** (`EXPIRY_NEEDS_CHECK_DAYS`): `needs_check` + email/in-app "Still available?" with a signed one-tap link (no login required) to confirm or mark taken.
- **Day 30** (`EXPIRY_EXPIRE_DAYS`): `expired` (hidden; owner can restore in one tap).
- **Day 90** (`EXPIRY_ARCHIVE_DAYS`): `archived`, delete photos, keep stats.
- Per-section overrides via constance JSON `SECTION_EXPIRY_OVERRIDES`; events expire after `ends_at`; jobs after `deadline`; food after `available_until`; alerts after `valid_until`.
- Auto-hide any listing with ≥ `REPORTS_AUTO_HIDE` (3) open reports pending moderator review.

### 6.7 Engagement

- **Like** (heart) toggle via HTMX; updates Saved list and counters; logs `like`/`unlike`.
- **Comments:** logged-in only; owner replies labelled "Owner"; owner can hide; **mask** Ghana phone numbers (e.g. `+233…`, `0XX XXX XXXX` with spaces/dashes), emails and URLs to `[hidden]`; notify owner.
- **Reviews** for hostels and users after contact (only users who started a conversation about the hostel/listing may review).
- **Report** buttons on listings, comments, users, conversations.
- **Saved searches:** "Alert me" on any filtered page; daily task notifies on new matches.
- **Share:** Web Share API with copy-link fallback and a "Share to WhatsApp" button; logs `share`.

### 6.8 Chat

- Conversation per (listing, starter). Participants appear under aliases: `<CAMPUS_SHORT> Student #<alias_number>` for students, `KampusDey User #<alias_number>` otherwise.
- HTMX polling: every 5s on an open conversation, every 30s for the unread badge.
- **"Share my number"** posts a `shared_contact` message with the sender's chosen channel.
- **Block** and **Report conversation**. Admins can read a conversation only through a report.
- **Scam warning:** messages matching `BannedTerm` rows with action `warn` (seed: "momo", "mobile money", "deposit", "send money", "pay first", "transfer") show a banner: "Never pay before viewing the room."
- New-account message limits (§6.2).

### 6.9 Notifications and PWA

- In-app notifications (bell + list), email notifications (batched at most every 15 minutes), and **web push** (django-webpush) when the user opts in.
- Triggers: new message, new comment/question, reply to your question, saved-search match, "Still available?" check, boost ended, verification decision, campus request result.
- **NotificationPreference** per user: email on/off per trigger, weekly digest on/off, push on/off.
- **PWA:** manifest, icons, service worker that caches static assets and an offline fallback page only (network-first for HTML; never cache tiles or authenticated responses).

### 6.10 Hostel Manager

- Dashboard for users with role landlord/agent: create/edit a Hostel, room types with `total_rooms` / `available_rooms` steppers, photos, rules, amenities.
- Public hostel page `/h/<slug>/` with room types, availability, reviews and contact bar.
- Inquiries inbox: conversations and contact taps for the hostel's listings.
- Occupancy overview and stats per room type (views, taps, likes).

### 6.11 Moderation and safety

- **Rules engine** (`moderation/services.py`) runs on create/update of listings, comments and messages:
  - Price sanity: reject negative prices; send prices outside the category's `min_price`/`max_price` to review.
  - Duplicate detection: same owner + similar title (trigram similarity ≥ 0.8) or matching photo `phash` (Hamming distance ≤ 6) → block with a friendly message; near-duplicates across owners → review.
  - BannedTerm actions: `block` / `review` / `warn`. Seed examples: get-rich courses, buying followers/group members, counterfeit.
- **Moderation queue** in the admin with approve/reject bulk actions.
- **Student seller vs Business** badge on cards; "Students only" filter on Buy & Sell, Services and Free & Leaving.
- **Scam alert board** page listing published ScamAlerts.
- django-ratelimit on sign-up, login, posting, comments, messages, email relay, OTP; django-axes for login lockouts (purge records after 30 days); django-auditlog on Listing, Profile, VerificationRequest, IntegrationSettings, Boost, Report.
- **CSP** via django-csp; Alpine CSP build; allow the tile host in `img-src`; HTMX requests send the CSRF token header.
- Uploads: content-type sniffing, size limits, Pillow verify, EXIF strip, randomised filenames.
- Staff admin at a configurable path (`ADMIN_URL` env).

### 6.12 Telemetry and analytics

- Record events: `view` (listing detail, server-side), `tap` (contact buttons, via HTMX POST before revealing/redirecting; `meta.channel`), `like`/`unlike`, `share`, `search` (`meta.query`, `meta.results`), `boost`.
- **Dedupe views:** one per (session_hash, listing, day) using a Redis key with 24h TTL. Ignore known bots by user agent.
- **Write path:** push events to a Redis list; a Celery task every 60s bulk-creates them. Never block the request.
- **Location on events:** from the user's chosen campus/town; GeoLite2 region only as fallback in `meta.region`. **No raw IPs stored.**
- **Nightly roll-up** into DailyListingStats and DailyCampusStats; update `views_7d`, `taps_7d` counters; delete raw events older than `TELEMETRY_RAW_RETENTION_DAYS` (90).
- **Poster dashboard:** per listing and per week — views, taps by channel, likes, shares, comments; boosts left this week.
- **Admin analytics** (unfold dashboard): today/7d/30d KPIs (sign-ups, posts, active listings, views, taps), charts by campus, region and section, top searches, **zero-result searches (search gap report)**, pending queues.
- **Umami** (optional): if `umami_script_url` and `umami_website_id` are set, include the script tag in `base.html`.

### 6.13 Growth

- **Campus ambassadors:** referral links `/r/<code>/`; when a referred user verifies their email and makes a first post, credit `AMBASSADOR_BONUS_BOOSTS`.
- **Weekly "new near you" digest** email (opt-out).
- **Rent check** page per campus: median and range of rent by area and room type from active + recently taken room listings (show only when ≥ 5 samples).
- **Student Business of the Week** spotlight on home.
- **SEO:** clean URLs; `sitemap.xml` (campuses, sections, active listings, hostels); canonical tags; Open Graph + Twitter meta with the first photo; JSON-LD `JobPosting` for jobs posted on KampusDey and `Event` for events; `robots.txt`. **External jobs (Remotive) never get JobPosting data, are excluded from sitemaps and carry `noindex`.**
- **Empty states** everywhere with a clear call to action.

### 6.14 Admin dashboard and settings

- django-unfold with grouped sidebar: Listings, Hostels, Locations, Users, Moderation, Engagement, Telemetry, Growth, Settings.
- **Constance settings** (with these defaults):

| Key | Default |
|---|---|
| EXPIRY_NEEDS_CHECK_DAYS / EXPIRY_EXPIRE_DAYS / EXPIRY_ARCHIVE_DAYS | 14 / 30 / 90 |
| SECTION_EXPIRY_OVERRIDES | `{}` (JSON) |
| FOOD_POST_MAX_HOURS | 6 |
| BOOSTS_PER_WEEK / BOOST_DURATION_DAYS / BOOST_SLOTS_PER_PAGE / BOOST_MIN_ACCOUNT_AGE_HOURS | 2 / 3 / 4 / 24 |
| W_FRESH / W_ACT / W_QUAL / W_REPORT / ACTIVITY_CAP / FRESH_HALF_LIFE_DAYS | 1.0 / 1.0 / 0.3 / 0.5 / 3.0 / 7 |
| NEARBY_RADII | `500,1000,2000` |
| CAMPUS_AUTOLINK_RADIUS_M / LOCATION_SNAP_M / WALKING_M_PER_MIN | 3000 / 200 / 80 |
| NEW_SELLER_REVIEW_COUNT / REPORTS_AUTO_HIDE | 3 / 3 |
| FIRST_CONTACT_MIN_ACCOUNT_AGE_HOURS / CHAT_NEW_ACCOUNT_DAYS / CHAT_NEW_ACCOUNT_DAILY_LIMIT | 24 / 3 / 20 |
| MAX_PHOTOS / MAX_UPLOAD_MB | 8 / 8 |
| MAP_TILE_URL | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` |
| MAP_ATTRIBUTION | `© OpenStreetMap contributors` (linked to the OSM copyright page) |
| THEMES_OFFERED | `system,kampusdey,kampusdey-dark,cupcake,emerald,corporate,garden,lofi,retro,nord,night,coffee,dracula,sunset` |
| TELEMETRY_RAW_RETENTION_DAYS | 90 |
| AMBASSADOR_BONUS_BOOSTS | 2 |

- **SectionAvailability** admin with a per-campus matrix view.
- **IntegrationSettings** page (superadmin only) with "Send test email", "Send test SMS" and "Update GeoLite2 now" actions.
- Queues: moderation, reports, verification requests, campus requests — each with counts on the dashboard.

---

## 7. UI/UX and theming

### 7.1 Layout

- **Mobile (< 1024px):** top header (logo, campus switcher, search icon, notifications bell) + **bottom navigation**: Home · Nearby · **+ Post** (prominent centre button) · Chats · Profile.
- **Desktop (≥ 1024px):** left sidebar navigation, centred content column (max ~1200px), same components.
- Rounded cards, generous spacing, one typeface (self-hosted Inter variable font), Lucide icons, skeleton loaders (no spinners), toast messages for actions.
- Currency formatting via a `ghs` template filter: `GH₵ 1,200`.

### 7.2 Themes (Tailwind v4 + daisyUI 5)

`static/src/styles.css`:

```css
@import "tailwindcss";
@source "../../templates";
@source "../../apps";

@plugin "daisyui" {
  themes: cupcake, emerald, corporate, garden, lofi, retro, nord, night, coffee, dracula, sunset;
}

@plugin "daisyui/theme" {
  name: "kampusdey";
  default: true;
  prefersdark: false;
  color-scheme: light;
  --color-base-100: #FFFFFF;
  --color-base-200: #F5F7F6;
  --color-base-300: #E6EBE9;
  --color-base-content: #1F2937;
  --color-primary: #0E7C66;
  --color-primary-content: #FFFFFF;
  --color-secondary: #F2B705;
  --color-secondary-content: #1F2937;
  --color-accent: #E8573F;
  --color-accent-content: #FFFFFF;
  --color-neutral: #1F2937;
  --color-neutral-content: #F9FAFB;
  --color-info: #2563EB;
  --color-info-content: #FFFFFF;
  --color-success: #16A34A;
  --color-success-content: #FFFFFF;
  --color-warning: #F59E0B;
  --color-warning-content: #1F2937;
  --color-error: #DC2626;
  --color-error-content: #FFFFFF;
  --radius-selector: 1rem;
  --radius-field: 0.75rem;
  --radius-box: 1rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 1;
  --noise: 0;
}

@plugin "daisyui/theme" {
  name: "kampusdey-dark";
  default: false;
  prefersdark: true;
  color-scheme: dark;
  --color-base-100: #0F1715;
  --color-base-200: #16201D;
  --color-base-300: #1F2B27;
  --color-base-content: #E5ECEA;
  --color-primary: #2BB596;
  --color-primary-content: #062018;
  --color-secondary: #F5C842;
  --color-secondary-content: #1F2937;
  --color-accent: #FF7A5C;
  --color-accent-content: #1F0B06;
  --color-neutral: #2A3632;
  --color-neutral-content: #E5ECEA;
  --color-info: #60A5FA;
  --color-info-content: #0B1220;
  --color-success: #4ADE80;
  --color-success-content: #052E16;
  --color-warning: #FBBF24;
  --color-warning-content: #1F1300;
  --color-error: #F87171;
  --color-error-content: #2A0505;
  --radius-selector: 1rem;
  --radius-field: 0.75rem;
  --radius-box: 1rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 1;
  --noise: 0;
}
```

Theme behaviour:
- The theme is applied as `data-theme` on `<html>`.
- `system` = `kampusdey` or `kampusdey-dark` following `prefers-color-scheme`, updating live when the device setting changes.
- A tiny inline script in `<head>` (CSP nonce) applies the saved theme **before first paint** (no flash). Source of truth: `User.theme` for logged-in users (rendered server-side), `localStorage["kd-theme"]` for guests.
- **Profile → Appearance** shows only themes in `THEMES_OFFERED` as preview swatches; choosing one updates immediately and saves (HTMX POST for users, localStorage for guests).
- Every component must look correct in all offered themes: use daisyUI semantic colours (`bg-base-100`, `text-base-content`, `btn-primary`…), never hard-coded colours.

### 7.3 Cotton components (in `templates/cotton/`)

`listing-card`, `listing-card-skeleton`, `section-chip`, `price`, `badge-verified`, `badge-seller-type`, `contact-bar`, `contact-button`, `photo-carousel`, `photo-uploader`, `map` (Leaflet wrapper with attribution and approximate-circle mode), `location-picker`, `campus-switcher`, `theme-picker`, `bottom-nav`, `sidebar-nav`, `empty-state`, `modal`, `bottom-sheet`, `stepper` (wizard), `form-field`, `alert`, `toast`, `stat`, `avatar`, `like-button`, `share-button`, `report-button`, `comment-thread`, `chat-bubble`, `pagination-sentinel` (HTMX infinite scroll).

### 7.4 Performance and accessibility

- Budget: CSS + JS on first load ≤ 200 KB gzipped excluding images; Leaflet loaded only on pages with maps.
- Images lazy-loaded with `srcset` from WebP renditions and explicit width/height.
- Target LCP < 2.5s on a mid-range Android over 4G.
- Labels on all inputs, visible focus states, ≥ 44px tap targets, WCAG AA contrast in both brand themes, `prefers-reduced-motion` respected.

---

## 8. Configuration, environment and integrations

### 8.1 Environment variables (`.env.example`)

`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `ADMIN_URL`, `DATABASE_URL`, `REDIS_URL`, `FIELD_ENCRYPTION_KEY`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (optional), `STORAGE_BACKEND` (local|s3), `AWS_*`/R2 settings, `PRIVATE_STORAGE_BUCKET`, `SENTRY_DSN`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_ADMIN_EMAIL`, `GEOIP_PATH`, `SITE_URL`, `MAP_USER_AGENT` (e.g. `KampusDey/1.0 (+https://<domain>/contact)`).

### 8.2 Email

SMTP from env at launch. Document SPF, DKIM and DMARC setup for the sending domain in `docs/OPERATIONS.md`.

### 8.3 Encrypted secrets

`EncryptedTextField` using Fernet; key rotation documented; secrets never logged, never rendered back in the admin.

---

## 9. Testing and quality

- pytest + pytest-django + factory_boy. Every app has model, service and view tests. Coverage ≥ 80% on `services.py` / `selectors.py`.
- Key behaviours that must have tests: permission helpers and interim rules; boost limits; lifecycle transitions; ranking formula; campus auto-link radius; location snapping; contact visibility (numbers never in HTML for guests); comment masking; moderation rules (price, duplicates, banned terms); telemetry dedupe and roll-ups; theme persistence; OTP flow; verification document deletion; account deletion.
- GitHub Actions: ruff, format check, tests against a PostGIS service container, migrations check (`makemigrations --check`).
- Milestone 14 adds Playwright smoke tests for: picker → home, post wizard, contact reveal, like, chat send, theme switch.

---

## 10. Milestones and acceptance criteria

### M0 — Foundation and theming
Repo, `uv`, settings split, env handling, Docker Compose (web, worker, beat, db, redis, mailpit), custom User, `core` app, Makefile, pre-commit, ruff, pytest, CI, README, `docs/PROGRESS.md`, `docs/ARCHITECTURE.md`. Tailwind v4 + daisyUI 5 build with both brand themes, `base.html` with header, bottom nav, sidebar, theme picker and no-flash script; constance and unfold installed.
**Accept:** `make up` serves a themed home page; theme switching persists for guests; dark mode follows the device under `system`; CI green.

### M1 — Locations
Region/Town/Campus/Area/CampusRequest models + admin (GIS widgets), `seed_locations` command (16 regions + starter campus names from Appendix A, points null), location picker, campus switcher, follow campuses, CampusRequest flow, GeoIP hint, `update_geolite2` command + weekly task.
**Accept:** guest and user can pick campus/town or "Other"; choice persists; nearest-campus suggestion works when campus points exist; missing GeoLite2 DB causes no errors; no coordinates invented.

### M1.5 — Real location data import
Follow `docs/DATA_SOURCES_PROMPT.md` in full: Institution model, provenance fields, region boundaries, importers for Wikidata, OpenStreetMap, HDX, GTEC and Ministry of Health lists, matching, admin review queue, Data sources page, quarterly refresh.
**Accept:** the acceptance criteria in §12 of `docs/DATA_SOURCES_PROMPT.md`.

### M2 — Accounts and verification
allauth email accounts (mandatory verification), optional Google, staff MFA, Turnstile, onboarding, profile, aliases, permission helpers with interim rules, phone OTP flow behind the runtime switch with console SMS backend, IntegrationSettings with encrypted fields, VerificationRequest with private storage and auto-deletion, badges, account deletion, data export.
**Accept:** unverified users cannot post/comment/like/chat; switching `require_phone_verification` on forces OTP at next login (console backend prints the code); documents are deleted after a decision; secrets are unreadable in the database.

### M3 — Listing core, contacts, post wizard, photos
Listing + ListingCampus + ListingPhoto, categories, ContactCard/Channel + handler registry, 3-step HTMX wizard with drafts, photo pipeline (validation, EXIF strip, WebP renditions, phash), location snapping, campus auto-link with manual edits, listing detail page with sticky contact bar, contact visibility and phone reveal.
**Accept:** a user can post a Buy & Sell item end to end on a phone-sized screen; guest viewing a members-only post sees no contact details in the HTML; uploaded images have no EXIF.

### M4 — All sections
All 18 details models, forms, card info lines, detail partials, section rules (food expiry and members-only need-food; events/jobs/alerts expiry fields; trips disabled by default), SectionAvailability with per-campus matrix.
**Accept:** every section can be posted, viewed and filtered; disabled sections disappear from chips, URLs return 404 and the post picker hides them.

### M5 — Discovery, ranking and maps
Home feeds, section pages with filters and sorts, full-text search with facets, ranking task, boosted slot rotation, Leaflet maps (configurable tiles + attribution), Nearby page with radius rings, walking minutes, approximate circles for sensitive sections, empty states, infinite scroll.
**Accept:** sort by distance works from geolocation and from the chosen campus; no tile caching in the service worker; attribution visible on every map.

### M6 — Lifecycle, boosts and poster dashboard
Pending review for new sellers, needs-check emails with signed one-tap links, expire/archive tasks with photo deletion, per-section overrides, report auto-hide, free boosts with all limits, poster dashboard (listings, statuses, renew, mark taken, boosts left).
**Accept:** time-travel tests prove every transition; a third boost in 7 days is refused with a clear message; boosts end when a listing is taken.

### M7 — Engagement
Likes/Saved, comments with masking and owner labels, reviews, reports, saved searches with daily alerts, share buttons.
**Accept:** masked numbers/emails/links never reach the database unmasked; saved-search alerts fire only for new matches.

### M8 — Chat, notifications and PWA
Conversations with aliases, HTMX polling, share-my-number, block/report, scam warnings, message limits, in-app/email/web-push notifications with preferences, PWA manifest and service worker with offline page.
**Accept:** two users can chat on mobile; blocked users cannot message; scam keywords show the banner; email notifications are batched.

### M9 — Hostel Manager
Hostel, room types, availability steppers, linked room listings auto-taken at zero availability, public hostel page, inquiries inbox, occupancy and stats.
**Accept:** setting availability to 0 hides the linked listing from search; raising it restores it.

### M9.5 — External content: places around campus and remote jobs
Follow Part 2 of `docs/DATA_SOURCES_PROMPT.md`: Source registry, OpenStreetMap places with the Around campus directory and claim flow (claimed accommodation becomes a Hostel), Remotive remote jobs tab, partner-feed adapter, admin screens.
**Accept:** the acceptance criteria in §20 of `docs/DATA_SOURCES_PROMPT.md`.

### M10 — Moderation and safety
Rules engine (price ranges, duplicates, banned terms), moderation queue, seller-type badges + "Students only" filter, scam alert board, rate limits, axes, auditlog, CSP, upload hardening, configurable admin URL.
**Accept:** negative prices rejected; duplicate posts blocked; banned-term posts go to review; CSP reports no violations on key pages.

### M11 — Telemetry and analytics
Event buffer + flush, dedupe, bot filtering, roll-ups, retention cleanup, poster stats, admin analytics dashboard with search-gap report, optional Umami.
**Accept:** repeated views in one day count once; no IP addresses in telemetry tables; dashboard charts render with seeded demo data in dev.

### M12 — Growth and SEO
Ambassadors and referrals, weekly digest, rent check, spotlight, sitemaps, meta/OG, JSON-LD, robots.txt.
**Accept:** structured data validates for a job and an event; share previews show title, price and photo.

### M13 — Admin polish and operations
Unfold navigation and dashboard KPIs, constance groups, SectionAvailability matrix, IntegrationSettings test actions, queue counters, `docs/OPERATIONS.md` (env, backups, GeoLite2, switching tile provider, enabling phone verification, email DNS records, data protection checklist).
**Accept:** an admin can change every setting listed in §6.14 without a deploy.

### M14 — Hardening and launch readiness
Production Dockerfile (gunicorn), WhiteNoise, S3/R2 storage, Sentry, security settings (HSTS, secure cookies, SSL redirect), database backup script, performance pass (query counts, indexes, `select_related`/`prefetch_related`), accessibility pass, Playwright smoke tests, final README.
**Accept:** `manage.py check --deploy` clean; Lighthouse mobile ≥ 90 for Performance and Accessibility on home and listing pages; smoke tests green.

---

## 11. Definition of done (whole project)

- All milestones accepted and recorded in `docs/PROGRESS.md`.
- Every section works end to end on a 360px-wide screen in every offered theme.
- No payment code; no secrets in the repository; no raw IPs in telemetry; no invented real-world data.
- Admin can run the platform day to day without code changes.

## 12. Out of scope for this build

Payments (Paystack), native mobile apps and a public API, real-time WebSockets (Django Channels), production SMS provider integrations beyond the interface and stubs, AI features, and any scraping of listings or personal data from other platforms.

---

## Appendix A — Starter campus seed (names only; a fallback used by `seed_locations` in M1 before the M1.5 import runs; admins verify names)

| Campus | Short name | Kind | Town | Region |
|---|---|---|---|---|
| University of Energy and Natural Resources | UENR | university | Sunyani | Bono |
| Sunyani Technical University | STU | technical_university | Sunyani | Bono |
| Catholic University of Ghana | CUG | university | Fiapre | Bono |
| Berekum College of Education | BCoE | college_of_education | Berekum | Bono |
| Nurses and Midwifery Training College, Sunyani | NMTC Sunyani | nursing_midwifery | Sunyani | Bono |
| University of Ghana | UG | university | Legon | Greater Accra |
| University of Professional Studies, Accra | UPSA | university | Accra | Greater Accra |
| Ghana Communication Technology University | GCTU | university | Accra | Greater Accra |
| Accra Technical University | ATU | technical_university | Accra | Greater Accra |
| Kwame Nkrumah University of Science and Technology | KNUST | university | Kumasi | Ashanti |
| Kumasi Technical University | KsTU | technical_university | Kumasi | Ashanti |
| University of Cape Coast | UCC | university | Cape Coast | Central |
| Cape Coast Technical University | CCTU | technical_university | Cape Coast | Central |
| University of Education, Winneba | UEW | university | Winneba | Central |
| Takoradi Technical University | TTU | technical_university | Takoradi | Western |
| University of Mines and Technology | UMaT | university | Tarkwa | Western |
| Koforidua Technical University | KTU | technical_university | Koforidua | Eastern |
| Ho Technical University | HTU | technical_university | Ho | Volta |
| University of Health and Allied Sciences | UHAS | university | Ho | Volta |
| University for Development Studies | UDS | university | Tamale | Northern |
| Tamale Technical University | TaTU | technical_university | Tamale | Northern |
| Bolgatanga Technical University | BTU | technical_university | Bolgatanga | Upper East |

The seed command must be idempotent (`update_or_create` by slug) so admins can extend the list safely.
