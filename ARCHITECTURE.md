# EasyAgric — Architecture

Django REST API backend for a mobile app serving African smallholder farmers. Core flow: a farmer photographs their soil, the app sends it + GPS coords to the backend, which uses Google Gemini vision to analyze the soil, cross-references live weather data, and returns ranked crop recommendations — translated into the farmer's language, emailed, and pushed to their device.

## Tech stack

| Layer | Technology |
|---|---|
| Framework | Django 6.0 + Django REST Framework |
| Auth | JWT (`djangorestframework-simplejwt`) + custom email-based login + OTP-based password reset |
| Database | Postgres via `dj_database_url` (Neon Postgres in production), SQLite fallback locally (`config/settings.py:72-77`) |
| AI/Vision | Google Gemini Flash via `google-genai` SDK, model from `GEMINI_MODEL` (default `gemini-3.6-flash`) (`apps/soil/services.py`) |
| Weather | Open-Meteo free API, no auth required (`apps/weather/services.py`) |
| Translation | Google Cloud Translation API v2, REST calls (`apps/utils/email_translate.py`) |
| Push notifications | Firebase Cloud Messaging via `firebase-admin` (`apps/notifications/services.py`) |
| Email | `django-anymail` with Resend HTTP backend (falls back to SMTP), sent from background threads |
| Media storage | Local FS in dev, Cloudinary in production when configured (`config/settings.py:109-122`) |
| Static files | Whitenoise (`CompressedManifestStaticFilesStorage`) |
| Deployment | Render.com, `build.sh` (uv-based install + collectstatic), Gunicorn WSGI server |

## Apps

- **`apps/users`** — Custom `User(AbstractUser)` model (`apps/users/models.py:9-81`) with `role` (farmer/admin/appmanager), `language` (19 choices — African languages plus en/fr/es/pt), `phone`, `farm_name`. `is_privileged` lets staff/admin/appmanager skip GPS requirements elsewhere. `OTP` model (6-digit code, 10-min expiry, single-use) drives password reset. Custom `EmailBackend` (`apps/users/backends.py`) authenticates by email. Endpoints under `/api/auth/`: `languages/`, `register/`, `register/app-manager/` (admin-only), `login/`, `token/refresh/`, `me/`, `password/change/`, `password-reset/request/` + `password-reset/verify/`. Platform-admin account management lives in `AdminUserListView` / `AdminUserDetailView` behind `IsPlatformAdmin` (role `admin` or superuser — app managers excluded, as `is_privileged` is too broad to destroy accounts): `GET users/` lists accounts newest-first with their ids (filters `role`/`is_active`/`search` over email or farm name; `limit`/`offset` paging capped at 500) returning `{count, limit, offset, results}` so a truncated page is never mistaken for the whole set, `GET users/<pk>/` returns a `deletion_impact` breakdown computed from Django's own `Collector` (counting both `data` and `fast_deletes`, so it stays correct as models are added), `PATCH users/<pk>/` toggles `is_active` as the reversible option, and `DELETE users/<pk>/` erases the account and its cascade. Refusing self-deletion is the whole lockout guarantee — the caller is an active admin who cannot remove themselves, so one always survives; a separate "last admin" check would be unreachable. Deleting an account with **confirmed payments** returns 409 rather than silently destroying financial records, overridable with `?force=true`; `Payment.recorded_by`/`reviewed_by` are `SET_NULL`, so removing a staff member never destroys a farmer's payment history. Covered by `apps/users/tests.py` (24 tests). A `post_migrate` signal auto-creates a default admin (`apps/users/apps.py:15-33`); `ensure_superuser` management command also runs on every deploy from `DJANGO_SUPERUSER_*` env vars.

- **`apps/soil`** — `services.py::analyze_soil_image` sends the raw image bytes + a strict JSON-schema prompt to Gemini Flash (`settings.GEMINI_MODEL`), requesting soil_type, color, texture, moisture, organic matter, pH estimate, fertility, visible issues, amendments, confidence — in the user's language. `POST /api/soil/analyze/` (auth required, multipart image). Stateless — no models.

- **`apps/crops`** — `data.py` holds a static `CROP_DATABASE` dict keyed by 7 soil types (Clay, Sandy, Loam, Silt, Laterite, Black Cotton, Alluvial), each with crops (season months, temp range, water needs). `services.py::get_crop_recommendations(soil_type, current_temp)` scores each crop High/Medium/Low based on season + temperature fit, sorted best-first; `translate_crop_recommendations` batch-translates labels for non-English users. `GET /api/crops/recommend/?soil_type=&temp=`.

- **`apps/advisor`** — Orchestration/core-feature app. `AdvisorView` (`POST /api/advisor/`, auth required, multipart image+lat+lon) runs soil analysis (Gemini) and weather fetch (Open-Meteo) concurrently via `ThreadPoolExecutor`, derives crop recommendations, returns the response synchronously, then in a background daemon thread persists an `AnalysisRecord`, sends a translated HTML/text advice-report email, and pushes an FCM notification — all without blocking the HTTP response. Non-privileged users must supply GPS coordinates.

- **`apps/weather`** — `services.py::get_agricultural_data(lat, lon)` calls Open-Meteo for soil temperature (4 depths), soil moisture, and 7-day forecast. `GET /api/weather/?lat=&lon=`.

- **`apps/history`** — `AnalysisRecord` model: farmer FK, lat/lon, `soil_analysis`/`weather_data`/`crop_recommendations` as JSONFields, timestamped. `GET /api/history/` and `GET /api/history/<pk>/`, scoped to the requesting farmer.

- **`apps/dashboard`** — Read-only aggregate stats for admins/app managers (`DashboardPermission`: authenticated + privileged). `GET /api/dashboard/stats/`, `GET /api/dashboard/farmers/`, `GET /api/dashboard/farmers/<pk>/`.

- **`apps/notifications`** — `DeviceToken` model (user FK, unique token, platform android/ios). `services.py::send_push` lazily initializes Firebase from `FIREBASE_CREDENTIALS_JSON` and fires FCM multicast messages from a background thread. `POST /api/notifications/register/` (upsert by token), `POST /api/notifications/unregister/`.

- **`apps/subscriptions`** — Trial/paywall layer. `Subscription` (one per user) carries `plan`, `expires_at`, `analysis_quota`, `analyses_used`; `status` is *derived* from those fields (`active` / `expired` / `quota_exhausted` / `cancelled`) rather than stored, so trials expire without any cron job. Farmers get a 14-day, 5-analysis trial at registration (`Subscription.start_trial`, called from `RegisterView`); `Subscription.for_user` lazily starts one for accounts predating the feature. `HasAnalysisCredit` (`permissions.py`) gates the two image endpoints and raises `SubscriptionRequired` → **402** with a translated message, a machine-readable `code`, and a subscription snapshot. Credits are charged by `Subscription.consume_analysis` *after* a successful analysis (`SELECT FOR UPDATE` + `F()`), so failed Gemini calls are free; privileged users are never metered. Plan durations/quotas live in `Subscription.PLAN_CONFIG`; trial values come from `TRIAL_DAYS` / `TRIAL_ANALYSIS_QUOTA` in settings. Endpoints: `GET /api/subscriptions/plans/`, `GET /api/subscriptions/me/`, `POST /api/subscriptions/upgrade/` (privileged only — payment is out-of-band for now; a gateway webhook would call `subscription.upgrade(...)` instead).

  **Manual payments** (no gateway — cash and bank transfer, confirmed by hand): `PlanPrice` (plan × currency → amount) and `PaymentAccount` (bank details + cash contact, one per currency) live in the DB so ops can reprice or open a country from Django admin without a redeploy. `Payment` records one cash/bank-transfer payment with `status` (pending/confirmed/rejected), `reference`, optional `proof` ImageField (Cloudinary in prod), and `expected_amount` so the `shortfall` property flags underpayment. Farmers start the upgrade themselves via `POST /api/subscriptions/upgrade-request/` (`UpgradeRequestView`), which records a **pending** `Payment` before any money moves — no reference or receipt required, since `method` there is only the intended means of payment. Nothing activates: only a privileged confirm does that, and `SubscriptionSerializer.pending_upgrade` surfaces the waiting request everywhere the app already reads the subscription. A fresh request supersedes a previous un-evidenced one (so farmers can change their mind) but never touches a payment that carries a reference or receipt. Two further entry paths through `POST /api/subscriptions/payments/`: a farmer declaring their own transfer lands as **pending**, while a privileged user recording money they collected is **confirmed on creation** (they're holding the cash). `Payment.confirm()` is transactional and calls `subscription.upgrade(plan, months)`, then an email goes out via `apps/subscriptions/emails.py`. Endpoints: `GET payment-instructions/?currency=`, `GET|POST payments/`, `POST payments/<pk>/confirm/`, `POST payments/<pk>/reject/` (both privileged). `PaymentAdmin` exposes the pending queue with bulk confirm/reject actions. A fresh deploy has no prices, so `seed_payment_config` (`apps/subscriptions/management/commands/`) bootstraps `PlanPrice` + `PaymentAccount` rows from `PAYMENT_CONFIG_JSON` (or `--file`), following the same idempotent, silent-if-unset pattern as `ensure_superuser` and running from `render.yaml`'s start command; it **creates but never overwrites**, so prices edited in Django admin survive redeploys (`--overwrite` forces the JSON). `payment_config.example.json` is the fill-in template. Covered by `apps/subscriptions/tests.py` (50 tests).

- **`apps/utils`** — `email_translate.py`: wrapper around Google Cloud Translation REST API (`translate_email_content` for HTML/text blocks, `translate_batch` for lists of short strings). Falls back to original English text silently on missing key/unsupported language/failure. Used by `apps/users/emails.py`, `apps/advisor/emails.py`, `apps/crops/services.py`.

## Data flow: farmer gets crop recommendations

1. Farmer logs in (`POST /api/auth/login/`) → JWT access/refresh tokens.
2. Farmer app calls `POST /api/advisor/` with soil photo (multipart) + GPS lat/lon + `Authorization: Bearer <access>`. `HasAnalysisCredit` checks the subscription first — expired trial or exhausted quota short-circuits to 402.
3. `AdvisorView.post` (`apps/advisor/views.py:35-150`) validates input, then in parallel:
   - `soil.services.analyze_soil_image` → Gemini vision call → structured soil JSON.
   - `weather.services.get_agricultural_data` → Open-Meteo → current temp + soil temp/moisture + forecast.
4. `crops.services.get_crop_recommendations(soil_type, current_temp)` scores the static crop database.
5. One analysis credit is consumed (only if the soil analysis succeeded), then the response (soil analysis + weather + crop recommendations, translated to the user's `language`) is returned synchronously.
6. In a background thread: `AnalysisRecord` saved (`apps/history`), translated advice-report email sent (`apps/advisor/emails.py`), FCM push sent to registered device tokens (`apps/notifications/services.py`).
7. Farmer can later browse `GET /api/history/`; admins/app managers see aggregates via `/api/dashboard/`.

## Auth & authorization

- Login by **email + password**; `LoginSerializer` → `authenticate(email=..., password=...)` → custom `EmailBackend` looks up `User.objects.get(email=email)`.
- JWT via `rest_framework_simplejwt`: 30-min access, 7-day refresh, rotation + blacklist-after-rotation (`config/settings.py:199-207`).
- Password reset via OTP (6-digit, 10-min TTL, single-use), verified at `/api/auth/password-reset/verify/`.
- Roles: `farmer` (self-registers), `admin` (auto-seeded), `appmanager` (admin-created only). Permission classes `IsFarmer`/`IsAdminUser` in `apps/users/permissions.py`; `is_privileged` (staff or admin/appmanager) relaxes GPS requirements on advisor/weather endpoints.
- `language` field (19 choices) drives translation of outbound emails and crop-recommendation text.
- **Metering**: `/api/advisor/` and `/api/soil/analyze/` additionally require analysis credit via `HasAnalysisCredit`; admins/app managers bypass it.

## External integrations

- **Google Gemini** — soil image analysis, model from `GEMINI_MODEL` (default `gemini-3.6-flash`), key from `GEMINI_API_KEY`, called in `apps/soil/services.py`. The model id is deliberately configurable: Google retires model ids, and `gemini-2.0-flash` returning 404 once already broke soil analysis in production. Set `GEMINI_MODEL=gemini-flash-latest` to track the newest Flash automatically instead of pinning.
- **Google Cloud Translation API v2** — key from `GOOGLE_TRANSLATE_API_KEY` (`config/settings.py:180`); degrades to English on missing key/unsupported language/failure.
- **Open-Meteo** — free, keyless weather/soil API.
- **Firebase Cloud Messaging** — service-account JSON from `FIREBASE_CREDENTIALS_JSON`, parsed at runtime (`apps/notifications/services.py:22-35`).
- **Email** — `django-anymail` with Resend HTTP API backend if `RESEND_API_KEY` set (chosen to bypass Render free-tier SMTP blocking, see `config/settings.py:127-138`), else SMTP.
- **Cloudinary** — optional media storage, activated only if `CLOUDINARY_CLOUD_NAME` is set.
- **Database** — `DATABASE_URL` via `dj_database_url`; production uses Neon Postgres; local dev falls back to `db.sqlite3`.

## Deployment

- `render.yaml` defines a Render web service: `buildCommand: ./build.sh`, `startCommand: python manage.py migrate && python manage.py ensure_superuser && gunicorn config.wsgi:application`, Python 3.12.8. Several env vars (`DATABASE_URL`, Cloudinary, Resend, Firebase creds, superuser creds, Google Translate key) must be set manually in the Render dashboard; `DJANGO_SECRET_KEY` is auto-generated.
- `build.sh` runs `uv pip install -r requirements.txt` then `collectstatic --noinput`.
- Start command chains `migrate && ensure_superuser && seed_payment_config && gunicorn`; each management command is idempotent and no-ops when its env vars are unset.
- `config/settings.py:162-167` hardens production (`SECURE_SSL_REDIRECT`, secure cookies, CSRF trusted origins) when `DEBUG=False`, trusting Render's `X-Forwarded-Proto` header.
- Global exception handling: `config/exceptions.py` wraps unhandled DRF exceptions as JSON 500s, plus a `handler500` fallback for non-DRF errors.

## File reference index

- Settings: `config/settings.py`
- Root URLs: `config/urls.py`
- Custom user/OTP models: `apps/users/models.py`
- Email-based auth backend: `apps/users/backends.py`
- Advisor orchestration (core flow): `apps/advisor/views.py`
- Gemini soil analysis: `apps/soil/services.py`
- Crop recommendation engine: `apps/crops/services.py`, `apps/crops/data.py`
- Weather/soil data: `apps/weather/services.py`
- Push notifications: `apps/notifications/services.py`
- Translation helper: `apps/utils/email_translate.py`
- History model: `apps/history/models.py`
- Subscription model & paywall: `apps/subscriptions/models.py`, `apps/subscriptions/permissions.py`
- Dashboard stats: `apps/dashboard/views.py`
- Deployment: `render.yaml`, `build.sh`
