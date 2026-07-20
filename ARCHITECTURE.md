# EasyAgric — Architecture

Django REST API backend for a mobile app serving African smallholder farmers. Core flow: a farmer photographs their soil, the app sends it + GPS coords to the backend, which uses Google Gemini vision to analyze the soil, cross-references live weather data, and returns ranked crop recommendations — translated into the farmer's language, emailed, and pushed to their device.

## Tech stack

| Layer | Technology |
|---|---|
| Framework | Django 6.0 + Django REST Framework |
| Auth | JWT (`djangorestframework-simplejwt`) + custom email-based login + OTP-based password reset |
| Database | Postgres via `dj_database_url` (Neon Postgres in production), SQLite fallback locally (`config/settings.py:72-77`) |
| AI/Vision | Google Gemini 2.0 Flash via `google-genai` SDK (`apps/soil/services.py`) |
| Weather | Open-Meteo free API, no auth required (`apps/weather/services.py`) |
| Translation | Google Cloud Translation API v2, REST calls (`apps/utils/email_translate.py`) |
| Push notifications | Firebase Cloud Messaging via `firebase-admin` (`apps/notifications/services.py`) |
| Email | `django-anymail` with Resend HTTP backend (falls back to SMTP), sent from background threads |
| Media storage | Local FS in dev, Cloudinary in production when configured (`config/settings.py:109-122`) |
| Static files | Whitenoise (`CompressedManifestStaticFilesStorage`) |
| Deployment | Render.com, `build.sh` (uv-based install + collectstatic), Gunicorn WSGI server |

## Apps

- **`apps/users`** — Custom `User(AbstractUser)` model (`apps/users/models.py:9-81`) with `role` (farmer/admin/appmanager), `language` (19 choices — African languages plus en/fr/es/pt), `phone`, `farm_name`. `is_privileged` lets staff/admin/appmanager skip GPS requirements elsewhere. `OTP` model (6-digit code, 10-min expiry, single-use) drives password reset. Custom `EmailBackend` (`apps/users/backends.py`) authenticates by email. Endpoints under `/api/auth/`: `languages/`, `register/`, `register/app-manager/` (admin-only), `login/`, `token/refresh/`, `me/`, `password/change/`, `password-reset/request/` + `password-reset/verify/`. A `post_migrate` signal auto-creates a default admin (`apps/users/apps.py:15-33`); `ensure_superuser` management command also runs on every deploy from `DJANGO_SUPERUSER_*` env vars.

- **`apps/soil`** — `services.py::analyze_soil_image` sends the raw image bytes + a strict JSON-schema prompt to Gemini 2.0 Flash, requesting soil_type, color, texture, moisture, organic matter, pH estimate, fertility, visible issues, amendments, confidence — in the user's language. `POST /api/soil/analyze/` (auth required, multipart image). Stateless — no models.

- **`apps/crops`** — `data.py` holds a static `CROP_DATABASE` dict keyed by 7 soil types (Clay, Sandy, Loam, Silt, Laterite, Black Cotton, Alluvial), each with crops (season months, temp range, water needs). `services.py::get_crop_recommendations(soil_type, current_temp)` scores each crop High/Medium/Low based on season + temperature fit, sorted best-first; `translate_crop_recommendations` batch-translates labels for non-English users. `GET /api/crops/recommend/?soil_type=&temp=`.

- **`apps/advisor`** — Orchestration/core-feature app. `AdvisorView` (`POST /api/advisor/`, auth required, multipart image+lat+lon) runs soil analysis (Gemini) and weather fetch (Open-Meteo) concurrently via `ThreadPoolExecutor`, derives crop recommendations, returns the response synchronously, then in a background daemon thread persists an `AnalysisRecord`, sends a translated HTML/text advice-report email, and pushes an FCM notification — all without blocking the HTTP response. Non-privileged users must supply GPS coordinates.

- **`apps/weather`** — `services.py::get_agricultural_data(lat, lon)` calls Open-Meteo for soil temperature (4 depths), soil moisture, and 7-day forecast. `GET /api/weather/?lat=&lon=`.

- **`apps/history`** — `AnalysisRecord` model: farmer FK, lat/lon, `soil_analysis`/`weather_data`/`crop_recommendations` as JSONFields, timestamped. `GET /api/history/` and `GET /api/history/<pk>/`, scoped to the requesting farmer.

- **`apps/dashboard`** — Read-only aggregate stats for admins/app managers (`DashboardPermission`: authenticated + privileged). `GET /api/dashboard/stats/`, `GET /api/dashboard/farmers/`, `GET /api/dashboard/farmers/<pk>/`.

- **`apps/notifications`** — `DeviceToken` model (user FK, unique token, platform android/ios). `services.py::send_push` lazily initializes Firebase from `FIREBASE_CREDENTIALS_JSON` and fires FCM multicast messages from a background thread. `POST /api/notifications/register/` (upsert by token), `POST /api/notifications/unregister/`.

- **`apps/utils`** — `email_translate.py`: wrapper around Google Cloud Translation REST API (`translate_email_content` for HTML/text blocks, `translate_batch` for lists of short strings). Falls back to original English text silently on missing key/unsupported language/failure. Used by `apps/users/emails.py`, `apps/advisor/emails.py`, `apps/crops/services.py`.

## Data flow: farmer gets crop recommendations

1. Farmer logs in (`POST /api/auth/login/`) → JWT access/refresh tokens.
2. Farmer app calls `POST /api/advisor/` with soil photo (multipart) + GPS lat/lon + `Authorization: Bearer <access>`.
3. `AdvisorView.post` (`apps/advisor/views.py:35-150`) validates input, then in parallel:
   - `soil.services.analyze_soil_image` → Gemini vision call → structured soil JSON.
   - `weather.services.get_agricultural_data` → Open-Meteo → current temp + soil temp/moisture + forecast.
4. `crops.services.get_crop_recommendations(soil_type, current_temp)` scores the static crop database.
5. Response (soil analysis + weather + crop recommendations, translated to the user's `language`) returned synchronously.
6. In a background thread: `AnalysisRecord` saved (`apps/history`), translated advice-report email sent (`apps/advisor/emails.py`), FCM push sent to registered device tokens (`apps/notifications/services.py`).
7. Farmer can later browse `GET /api/history/`; admins/app managers see aggregates via `/api/dashboard/`.

## Auth & authorization

- Login by **email + password**; `LoginSerializer` → `authenticate(email=..., password=...)` → custom `EmailBackend` looks up `User.objects.get(email=email)`.
- JWT via `rest_framework_simplejwt`: 30-min access, 7-day refresh, rotation + blacklist-after-rotation (`config/settings.py:199-207`).
- Password reset via OTP (6-digit, 10-min TTL, single-use), verified at `/api/auth/password-reset/verify/`.
- Roles: `farmer` (self-registers), `admin` (auto-seeded), `appmanager` (admin-created only). Permission classes `IsFarmer`/`IsAdminUser` in `apps/users/permissions.py`; `is_privileged` (staff or admin/appmanager) relaxes GPS requirements on advisor/weather endpoints.
- `language` field (19 choices) drives translation of outbound emails and crop-recommendation text.

## External integrations

- **Google Gemini** — soil image analysis, model `gemini-2.0-flash`, key from `GEMINI_API_KEY` (`config/settings.py:177`), called in `apps/soil/services.py:49-69`.
- **Google Cloud Translation API v2** — key from `GOOGLE_TRANSLATE_API_KEY` (`config/settings.py:180`); degrades to English on missing key/unsupported language/failure.
- **Open-Meteo** — free, keyless weather/soil API.
- **Firebase Cloud Messaging** — service-account JSON from `FIREBASE_CREDENTIALS_JSON`, parsed at runtime (`apps/notifications/services.py:22-35`).
- **Email** — `django-anymail` with Resend HTTP API backend if `RESEND_API_KEY` set (chosen to bypass Render free-tier SMTP blocking, see `config/settings.py:127-138`), else SMTP.
- **Cloudinary** — optional media storage, activated only if `CLOUDINARY_CLOUD_NAME` is set.
- **Database** — `DATABASE_URL` via `dj_database_url`; production uses Neon Postgres; local dev falls back to `db.sqlite3`.

## Deployment

- `render.yaml` defines a Render web service: `buildCommand: ./build.sh`, `startCommand: python manage.py migrate && python manage.py ensure_superuser && gunicorn config.wsgi:application`, Python 3.12.8. Several env vars (`DATABASE_URL`, Cloudinary, Resend, Firebase creds, superuser creds, Google Translate key) must be set manually in the Render dashboard; `DJANGO_SECRET_KEY` is auto-generated.
- `build.sh` runs `uv pip install -r requirements.txt` then `collectstatic --noinput`.
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
- Dashboard stats: `apps/dashboard/views.py`
- Deployment: `render.yaml`, `build.sh`
