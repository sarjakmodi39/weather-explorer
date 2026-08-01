# Weather Explorer — Design

**Date:** 2026-08-01
**Context:** InRisk Labs full-stack case study. Build and deploy a weather explorer that fetches historical daily weather from Open-Meteo, stores the raw JSON in cloud object storage, and visualizes it in a dashboard.

## Goal

A live, publicly reachable dashboard backed by a live API, in a public GitHub repo with readable commit history. Every line must be explainable in a follow-up discussion — that constraint rules out unexplained dependencies and clever abstractions.

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Pydantic makes the graded validation declarative rather than hand-rolled; free OpenAPI docs at `/docs` for reviewers |
| Storage | Google Cloud Storage | Named first in the brief; 5GB always-free tier |
| Backend host | Cloud Run | Deploys a Dockerfile to an HTTPS URL in one command; 2M req/month free; scales to zero |
| Frontend | React + Vite + TypeScript + Tailwind | SPA is sufficient — every view is client-interactive, so SSR would add surface without benefit |
| Chart | Recharts | Declarative, small; hand-rolled SVG is more code to defend for no gain |
| Frontend host | Vercel (hobby, free) | Static build output |
| Tests | pytest + respx | Runs with no cloud credentials and no network |

## Repository layout

```
inrisk-weather-explorer/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              app factory, CORS, exception handlers
│  │  ├─ config.py            env-driven settings (GCS_BUCKET, ALLOWED_ORIGINS)
│  │  ├─ schemas.py           pydantic request/response models
│  │  ├─ errors.py            AppError → uniform JSON body
│  │  ├─ routes/weather.py    the three endpoints — thin, no business logic
│  │  └─ services/
│  │     ├─ open_meteo.py     httpx client for the archive API
│  │     └─ storage.py        StorageClient protocol + GCSStorage + InMemoryStorage
│  ├─ tests/
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/
│  └─ src/{api,components,hooks,lib}
├─ README.md
└─ DEPLOY.md
```

Separation of concerns: routes do HTTP, schemas do validation, services do I/O. Target under ~120 lines per file.

### The one abstraction that matters

`services/storage.py` defines a `StorageClient` protocol:

```python
class StorageClient(Protocol):
    def save_json(self, name: str, payload: dict) -> None: ...
    def list_files(self) -> list[StoredFile]: ...
    def get_json(self, name: str) -> dict | None: ...
```

Two implementations: `GCSStorage` (production) and `InMemoryStorage` (tests). Routes depend on the protocol through FastAPI dependency injection. This is what makes the backend testable without cloud credentials — the brief grades testability explicitly.

## Backend API

### `POST /store-weather-data`

Request: `{latitude, longitude, start_date, end_date}`

Validation, in order:

1. `latitude ∈ [-90, 90]`, `longitude ∈ [-180, 180]`
2. Dates parse as `YYYY-MM-DD`
3. `start_date <= end_date`
4. Inclusive day count `<= 31` — i.e. `(end - start).days <= 30`. Jun 1 → Jul 1 is 31 days and passes; Jun 1 → Jul 2 is 32 and fails. Stated in the README to preempt off-by-one disputes.
5. `end_date <= today (UTC)` and `start_date >= 1940-01-01` — the bounds Open-Meteo's archive itself enforces. Validated locally so the caller gets a clear 400 instead of a 502 wrapping an upstream error.

Any failure → `400` with `{"status": "error", "message": "<specific reason>"}`.

On success, calls `https://archive-api.open-meteo.com/v1/archive` with:

```
daily=temperature_2m_max,temperature_2m_min,
      apparent_temperature_max,apparent_temperature_min
timezone=auto
```

Stores the **unmodified** response body — the brief says "full API JSON", so no reshaping, no field stripping. Response: `{"status": "ok", "file": "<name>"}`.

**Filename format:** `weather_<lat>_<lon>_<start>_<end>_<timestamp>.json`

- lat/lon normalized to 4 decimal places, minus sign preserved (legal in GCS object names)
- timestamp is UTC basic ISO: `YYYYMMDDTHHMMSSZ`
- Example: `weather_-33.8688_151.2093_2024-06-01_2024-06-10_20260801T142530Z.json`

Normalizing precision makes names predictable — `19.076` and `19.0760` produce the same name rather than mirroring whatever the caller typed.

### `GET /list-weather-files`

Returns `{"files": [{"name", "size", "created_at"}]}`, sorted newest-first.

Efficiency: a single `list_blobs` call with a `fields` mask (`items(name,size,timeCreated),nextPageToken`) so GCS returns only the three needed fields. No per-object metadata fetches, no client-side filtering. Empty bucket returns `{"files": []}`, not an error.

### `GET /weather-file-content/{file}`

Returns the stored JSON.

The filename goes directly at a bucket, so it is a path-traversal surface. The name is validated against a strict regex matching our own naming pattern **before any storage call**. Anything that fails — traversal attempt, wrong prefix, junk — returns `404` with `{"status": "error", "message": "not found"}`, identical to a genuinely missing file.

Two reasons this is a 404 and not a 400: the brief specifies "missing/invalid → 404", and refusing to distinguish malformed from absent leaks nothing about bucket contents.

### Cross-cutting

**Error envelope.** Every error at every status code returns `{"status": "error", "message": "..."}`. The brief mandates that shape only for the 404, but a single contract is worth more to the frontend than per-case fidelity.

**Upstream failures.** Open-Meteo timeout or 5xx → `502`, message names Open-Meteo as the failing dependency. Open-Meteo `400` → surfaced as `400` with its `reason` passed through. 30s timeout, one retry.

**CORS.** Explicit origin allowlist from `ALLOWED_ORIGINS`, not `*`.

**Credentials.** No key file in the repo, ever. Cloud Run runs as a dedicated service account with object-admin on one bucket. Local dev uses ADC via `gcloud auth application-default login`. Only two config values: `GCS_BUCKET`, `ALLOWED_ORIGINS`.

### Verified API behavior

Probed live on 2026-08-01 before designing:

- Archive returns `daily` and `daily_units`; data available through 2 days ago with no nulls
- `end_date` beyond today → HTTP 400, `{"error": true, "reason": "Parameter 'end_date' is out of allowed range from 1940-01-01 to 2026-08-01"}`
- `start_date > end_date` → HTTP 400 with a `reason`

## Frontend

Single page. One column on mobile, two on desktop: input panel and file list left, chart and table right. Tailwind only — no component library.

**State model.** One piece of app state: `selectedFile` (name + parsed JSON). Chart, table, metadata, and pagination are all derived from it by pure functions. No duplicated copies of the weather data, so nothing can drift out of sync.

**Components — one job each:**

- `InputPanel` — lat/lon/start/end fields, plus preset locations. Client-side validation mirrors the server rules so obvious mistakes cost no round trip; the server remains the authority. On success, displays the returned filename and refreshes the file list.
- `FileList` — fetches on mount and after each successful store. Click loads content. Shows formatted size and created-at.
- `TempChart` — Recharts line chart, four series: `temperature_2m_max`, `temperature_2m_min`, `apparent_temperature_max`, `apparent_temperature_min`.
- `DataTable` — same four variables per day, 10/20/50 page-size selector.

**Avoiding excessive API calls.** Chart and table render from the JSON already in memory — never re-fetched. Loaded files are cached by name, so re-clicking is instant and silent. The browser never calls Open-Meteo; only the backend does.

**Loading and error states are per-region, not global.** Store, file list, and file content each own their spinner and error line. A failure in one panel does not blank the others. An empty bucket renders a real empty state, not an unresolved spinner.

**Null handling.** Open-Meteo can return `null` for an individual day. Those render as gaps in the line and `—` in the table, with the row retained — a partial file should look partial rather than short.

## Testing

Roughly 20 backend tests, running with no credentials and no network (`InMemoryStorage` via dependency override, Open-Meteo stubbed with `respx`):

- **Validation matrix** — lat/lon out of range, malformed dates, `start > end`, 32-day range, future `end_date`, missing fields. Each asserts status *and* message.
- **Happy path** — `{"status": "ok", "file": ...}`, filename matches the mandated pattern, stored bytes equal the unmodified API JSON.
- **List** — empty bucket → `{"files": []}`; populated bucket → correct metadata, newest-first.
- **Content** — round-trip; missing file → 404; traversal string → 404.
- **Upstream** — timeout → 502; Open-Meteo 400 → 400 with reason.

Frontend gets a thin slice, not a suite: pure-function tests for pagination math and the JSON→chart-series transform, where off-by-one bugs actually live. No React component test harness for a case study.

## Deployment

Backend and frontend cannot know each other's URLs until both exist, so step 4 is a deliberate second pass:

1. GCP project, bucket, service account. (User runs `gcloud auth login`.)
2. Backend → Cloud Run, `ALLOWED_ORIGINS` temporarily permissive. Verify all three endpoints with `curl`.
3. Frontend → Vercel, `VITE_API_BASE` set to the Cloud Run URL.
4. Redeploy backend with `ALLOWED_ORIGINS` locked to the real Vercel domain. Re-verify end to end.

**Cost:** Cloud Run always-free tier (2M requests/month) plus GCS 5GB free tier; scale-to-zero means idle costs nothing. Vercel hobby is free. README states last-verified-live date and a one-command redeploy path, as the brief requires.

**Commits:** one per meaningful unit — scaffold, storage layer, endpoints, tests, frontend components, deploy config. The brief states they read commit history.

## Out of scope

Deliberately excluded to keep the surface defensible: map-based location picking, city geocoding search, multi-file comparison, dark mode, authentication, a database, caching layers, and CI pipelines. None are required by the brief.

## Assumptions

1. "Range ≤ 31 days" means an inclusive day count of at most 31.
2. "Full API JSON" means the response body stored byte-for-byte, unmodified.
3. Date bounds beyond those listed in the brief (no future dates, nothing before 1940) are validated server-side, since Open-Meteo rejects them regardless.
4. A malformed filename and a missing filename are indistinguishable in the response — both 404.
5. Bucket contents stay small enough that unpaginated listing is appropriate; the `fields` mask keeps the single call cheap.
