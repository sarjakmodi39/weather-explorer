# Weather Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a full-stack weather explorer that fetches historical daily weather from Open-Meteo, stores raw JSON in Google Cloud Storage, and visualizes it in a React dashboard — live at public URLs.

**Architecture:** A FastAPI backend on Cloud Run exposes three endpoints (store / list / read) and owns all Open-Meteo and GCS access. Storage sits behind a `StorageClient` protocol with in-memory and GCS implementations, so the entire backend test suite runs with no cloud credentials and no network. A React + Vite SPA on Vercel calls the backend over CORS and renders a chart and paginated table from file JSON held in memory.

**Tech Stack:** Python 3.12, FastAPI 0.141, pydantic 2.13, google-cloud-storage 3.13, httpx 0.28, pytest 9.1, respx 0.23 · React 19, Vite 8, TypeScript 6, Tailwind CSS 4, Recharts 3.10 · Cloud Run, GCS, Vercel.

## Global Constraints

- **Verified toolchain.** All versions above were installed and smoke-tested on 2026-08-01. Pin them in `requirements.txt`; do not upgrade mid-implementation.
- **Tailwind 4 has no config file.** Setup is the `@tailwindcss/vite` plugin plus `@import "tailwindcss";` in CSS. Do **not** create `tailwind.config.js` or `postcss.config.js` — that is Tailwind 3 guidance and will not work.
- **Tests never touch the network or GCP.** Open-Meteo is stubbed with `respx`; storage uses `InMemoryStorage` via FastAPI dependency override.
- **No credential files in the repo, ever.** No service-account JSON keys. Cloud Run uses an attached service account; local dev uses ADC.
- **Uniform error envelope.** Every error response at every status code is exactly `{"status": "error", "message": "<text>"}`.
- **Date range rule:** inclusive day count ≤ 31, i.e. `(end_date - start_date).days <= 30`.
- **Filename format:** `weather_<lat:.4f>_<lon:.4f>_<start>_<end>_<YYYYMMDDTHHMMSSZ>.json`
- **Store the Open-Meteo response body unmodified.** No reshaping or field stripping.
- **Commit after every task.** The brief states commit history is reviewed. Use conventional-commit prefixes (`feat:`, `test:`, `chore:`, `docs:`).
- **Open-Meteo archive endpoint:** `https://archive-api.open-meteo.com/v1/archive`, daily variables `temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min`, `timezone=auto`.

### Verified behavior to rely on (probed live 2026-08-01)

- Archive returns `daily` (columnar arrays) and `daily_units`; data is available through ~2 days ago with no nulls.
- Future `end_date` → upstream HTTP 400, body `{"error": true, "reason": "Parameter 'end_date' is out of allowed range from 1940-01-01 to <today>"}`.
- `start_date > end_date` → upstream HTTP 400 with a `reason`.
- `google.cloud.storage.Client.list_blobs` accepts a `fields` kwarg. `Blob` exposes `.name`, `.size`, `.time_created`.
- **Validator ordering is observable.** In `model_validator(mode="after")`, checks run top-to-bottom and the first failure wins. Tests must isolate each rule — e.g. a future-date test must use `start_date=2099-01-01, end_date=2099-01-05`, because `start=2024-06-01, end=2099-01-01` trips the 31-day rule first.
- `starlette` 1.3.1 emits `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`. Cosmetic; ignore.

---

## File Structure

```
<repo root>/
├─ backend/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py              app factory, CORS, exception handlers   (Task 1, 9)
│  │  ├─ config.py            pydantic-settings Settings              (Task 1)
│  │  ├─ errors.py            AppError + handlers                     (Task 1)
│  │  ├─ schemas.py           request/response models + validation    (Task 2)
│  │  ├─ naming.py            filename build + validate               (Task 3)
│  │  ├─ deps.py              storage dependency provider             (Task 4)
│  │  ├─ routes/
│  │  │  ├─ __init__.py
│  │  │  └─ weather.py        the three endpoints                     (Tasks 6-8)
│  │  └─ services/
│  │     ├─ __init__.py
│  │     ├─ storage.py        StorageClient protocol + impls          (Task 4)
│  │     └─ open_meteo.py     archive API client                      (Task 5)
│  ├─ tests/
│  │  ├─ conftest.py          TestClient + storage override           (Task 4)
│  │  ├─ test_schemas.py                                              (Task 2)
│  │  ├─ test_naming.py                                               (Task 3)
│  │  ├─ test_storage.py                                              (Task 4)
│  │  ├─ test_open_meteo.py                                           (Task 5)
│  │  └─ test_routes.py                                               (Tasks 6-8)
│  ├─ Dockerfile                                                      (Task 9)
│  ├─ requirements.txt                                                (Task 1)
│  └─ .dockerignore                                                   (Task 9)
├─ frontend/
│  ├─ src/
│  │  ├─ main.tsx, index.css, App.tsx                                 (Tasks 10, 15)
│  │  ├─ types.ts             shared API types                        (Task 10)
│  │  ├─ api/client.ts        fetch wrappers                          (Task 10)
│  │  ├─ lib/transform.ts     pure: rows, paginate, validate          (Task 11)
│  │  ├─ lib/transform.test.ts                                        (Task 11)
│  │  ├─ hooks/useAsync.ts    loading/error state helper              (Task 12)
│  │  └─ components/
│  │     ├─ InputPanel.tsx                                            (Task 12)
│  │     ├─ FileList.tsx                                              (Task 13)
│  │     ├─ TempChart.tsx                                             (Task 14)
│  │     ├─ DataTable.tsx                                             (Task 14)
│  │     └─ StatusBanner.tsx                                          (Task 12)
│  ├─ .env.example
│  └─ vite.config.ts                                                  (Task 10)
├─ README.md                                                          (Task 17)
├─ DEPLOY.md                                                          (Task 16)
└─ .gitignore                                                         (Task 1)
```

---

## Task 1: Backend scaffold, config, and error envelope

**Files:**
- Create: `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/errors.py`, `backend/app/main.py`, `backend/pytest.ini`, `.gitignore`
- Test: `backend/tests/test_errors.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `app.config.Settings` with fields `gcs_bucket: str`, `allowed_origins: str`, `open_meteo_url: str`; `get_settings() -> Settings` (lru_cached)
  - `app.errors.AppError(message: str, status_code: int)` exception
  - `app.errors.error_body(message: str) -> dict` returning `{"status": "error", "message": message}`
  - `app.main.create_app() -> FastAPI` and module-level `app`

- [ ] **Step 1: Create the Python virtual environment and dependency file**

```bash
cd backend
python -m venv .venv
```

Create `backend/requirements.txt`:

```
fastapi==0.141.1
uvicorn[standard]==0.52.0
pydantic==2.13.4
pydantic-settings==2.14.2
google-cloud-storage==3.13.0
httpx==0.28.1
pytest==9.1.1
respx==0.23.1
```

Install:

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

> On macOS/Linux the interpreter is `.venv/bin/python`. Every `.venv/Scripts/python.exe` below translates the same way.

- [ ] **Step 2: Create `.gitignore` at the repo root**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
node_modules/
dist/
.env
.env.local
*.log
```

- [ ] **Step 3: Create `backend/pytest.ini`**

```ini
[pytest]
testpaths = tests
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 4: Write the failing test**

Create `backend/tests/test_errors.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_apperror_is_rendered_as_uniform_envelope():
    """Any AppError must surface as {"status": "error", "message": ...}."""
    from app.errors import AppError

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise AppError("teapot trouble", status_code=418)

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == 418
    assert response.json() == {"status": "error", "message": "teapot trouble"}


def test_unhandled_exception_does_not_leak_internals():
    app = create_app()

    @app.get("/explode")
    async def explode():
        raise RuntimeError("secret connection string")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/explode")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert "secret connection string" not in body["message"]


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 6: Create `backend/app/__init__.py`**

Empty file.

```bash
touch backend/app/__init__.py
```

- [ ] **Step 7: Create `backend/app/config.py`**

```python
"""Application settings, sourced from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Name of the GCS bucket holding stored weather files.
    gcs_bucket: str = ""

    # Comma-separated list of origins permitted by CORS.
    # Deliberately not "*" — see README.
    allowed_origins: str = "http://localhost:5173"

    open_meteo_url: str = "https://archive-api.open-meteo.com/v1/archive"

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is read once per process."""
    return Settings()
```

- [ ] **Step 8: Create `backend/app/errors.py`**

```python
"""A single error contract for the whole API.

Every failure — validation, not-found, upstream, or unexpected — leaves the
service as {"status": "error", "message": "..."}. One shape for the frontend
to parse is worth more than per-case fidelity.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Raised anywhere in the app to produce a controlled error response."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def error_body(message: str) -> dict:
    return {"status": "error", "message": message}


def _readable(exc: RequestValidationError) -> str:
    """Turn pydantic's first error into one human sentence.

    pydantic prefixes messages raised from validators with "Value error, ";
    strip it so the client sees the sentence we actually wrote.
    """
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"] if part != "body")
    message = str(first["msg"]).removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 400 rather than FastAPI's default 422 — the brief asks for 400.
        return JSONResponse(status_code=400, content=error_body(_readable(exc)))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(str(exc.detail)))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the real cause; return an opaque message so nothing leaks.
        logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=error_body("internal server error"))
```

- [ ] **Step 9: Create `backend/app/main.py`**

```python
"""Application factory."""

from fastapi import FastAPI

from app.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Explorer API",
        description="Fetches historical daily weather from Open-Meteo and stores it in GCS.",
        version="1.0.0",
    )

    register_error_handlers(app)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_errors.py -v`
Expected: PASS — 3 passed

- [ ] **Step 11: Commit**

```bash
git add .gitignore backend/
git commit -m "feat(api): scaffold FastAPI app with uniform error envelope"
```

---

## Task 2: Request validation schemas

**Files:**
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing from prior tasks
- Produces:
  - `app.schemas.StoreWeatherRequest` — pydantic model with `latitude: float`, `longitude: float`, `start_date: date`, `end_date: date`
  - `app.schemas.MAX_RANGE_DAYS = 31`, `app.schemas.EARLIEST_DATE = date(1940, 1, 1)`
  - `app.schemas.StoredFile` — `name: str`, `size: int`, `created_at: datetime`
  - `app.schemas.ListFilesResponse` — `files: list[StoredFile]`
  - `app.schemas.StoreWeatherResponse` — `status: str`, `file: str`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_schemas.py`:

```python
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import StoreWeatherRequest

VALID = {
    "latitude": 19.076,
    "longitude": 72.8777,
    "start_date": "2024-06-01",
    "end_date": "2024-06-10",
}


def build(**overrides) -> StoreWeatherRequest:
    return StoreWeatherRequest(**{**VALID, **overrides})


def test_accepts_a_valid_request():
    request = build()
    assert request.latitude == 19.076
    assert request.start_date == date(2024, 6, 1)


def test_accepts_boundary_coordinates():
    build(latitude=90, longitude=180)
    build(latitude=-90, longitude=-180)


@pytest.mark.parametrize("latitude", [90.01, -90.01, 1000])
def test_rejects_out_of_range_latitude(latitude):
    with pytest.raises(ValidationError, match="latitude"):
        build(latitude=latitude)


@pytest.mark.parametrize("longitude", [180.01, -180.01, -999])
def test_rejects_out_of_range_longitude(longitude):
    with pytest.raises(ValidationError, match="longitude"):
        build(longitude=longitude)


@pytest.mark.parametrize("bad", ["not-a-date", "2024-13-01", "06/01/2024", ""])
def test_rejects_malformed_dates(bad):
    with pytest.raises(ValidationError):
        build(start_date=bad)


def test_rejects_start_after_end():
    with pytest.raises(ValidationError, match="on or before"):
        build(start_date="2024-06-11", end_date="2024-06-10")


def test_accepts_single_day_range():
    request = build(start_date="2024-06-01", end_date="2024-06-01")
    assert request.start_date == request.end_date


def test_accepts_exactly_31_inclusive_days():
    """Jun 1 -> Jul 1 is 31 days counted inclusively, and must pass."""
    build(start_date="2024-06-01", end_date="2024-07-01")


def test_rejects_32_inclusive_days():
    with pytest.raises(ValidationError, match="31 days"):
        build(start_date="2024-06-01", end_date="2024-07-02")


def test_rejects_future_end_date():
    # Isolated from the range rule: validators short-circuit on first failure,
    # so both dates must sit in the future and be close together.
    future = date.today() + timedelta(days=365)
    with pytest.raises(ValidationError, match="future"):
        build(start_date=str(future), end_date=str(future + timedelta(days=3)))


def test_accepts_today_as_end_date():
    today = date.today()
    build(start_date=str(today - timedelta(days=3)), end_date=str(today))


def test_rejects_dates_before_the_archive_begins():
    with pytest.raises(ValidationError, match="1940-01-01"):
        build(start_date="1939-12-25", end_date="1939-12-31")


@pytest.mark.parametrize("missing", ["latitude", "longitude", "start_date", "end_date"])
def test_rejects_missing_fields(missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError, match=missing):
        StoreWeatherRequest(**payload)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/schemas.py`:

```python
"""Request and response models.

Validation lives here as declarative schema rather than scattered `if`
statements in the route, so the rules are readable in one place.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

# Inclusive day count. Jun 1 -> Jul 1 is 31 days and is allowed;
# Jun 1 -> Jul 2 is 32 and is not.
MAX_RANGE_DAYS = 31

# Open-Meteo's ERA5 archive does not go back further than this.
EARLIEST_DATE = date(1940, 1, 1)


class StoreWeatherRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, description="Degrees north, -90 to 90")
    longitude: float = Field(ge=-180, le=180, description="Degrees east, -180 to 180")
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_date_window(self) -> "StoreWeatherRequest":
        # Order matters: the first failing rule is the message the caller sees.
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")

        span = (self.end_date - self.start_date).days + 1
        if span > MAX_RANGE_DAYS:
            raise ValueError(
                f"date range must not exceed {MAX_RANGE_DAYS} days (requested {span})"
            )

        if self.end_date > date.today():
            raise ValueError("end_date must not be in the future")

        if self.start_date < EARLIEST_DATE:
            raise ValueError(f"start_date must not be earlier than {EARLIEST_DATE.isoformat()}")

        return self


class StoreWeatherResponse(BaseModel):
    status: str = "ok"
    file: str


class StoredFile(BaseModel):
    name: str
    size: int  # bytes
    created_at: datetime  # serialized as ISO 8601


class ListFilesResponse(BaseModel):
    files: list[StoredFile]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_schemas.py -v`
Expected: PASS — all tests green (24 cases after parametrization)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_schemas.py
git commit -m "feat(api): add request validation schemas with inclusive 31-day rule"
```

---

## Task 3: Object-name construction and validation

**Files:**
- Create: `backend/app/naming.py`
- Test: `backend/tests/test_naming.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `app.naming.build_object_name(latitude: float, longitude: float, start: date, end: date, now: datetime | None = None) -> str`
  - `app.naming.is_valid_object_name(name: str) -> bool`
  - `app.naming.OBJECT_NAME_PATTERN` — compiled `re.Pattern`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_naming.py`:

```python
from datetime import date, datetime, timezone

import pytest

from app.naming import build_object_name, is_valid_object_name

FIXED_NOW = datetime(2026, 8, 1, 14, 25, 30, tzinfo=timezone.utc)


def test_builds_the_documented_format():
    name = build_object_name(19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 10), FIXED_NOW)
    assert name == "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json"


def test_preserves_negative_coordinates():
    name = build_object_name(-33.8688, 151.2093, date(2024, 6, 1), date(2024, 6, 10), FIXED_NOW)
    assert name == "weather_-33.8688_151.2093_2024-06-01_2024-06-10_20260801T142530Z.json"


def test_normalizes_coordinate_precision():
    """19.076 and 19.0760 must produce the same name — names are predictable,
    not a mirror of whatever the caller typed."""
    a = build_object_name(19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    b = build_object_name(19.07600, 72.87770, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    assert a == b


def test_pads_and_rounds_to_four_decimals():
    name = build_object_name(5, -0.123456, date(2024, 6, 1), date(2024, 6, 2), FIXED_NOW)
    assert "weather_5.0000_-0.1235_" in name


def test_generated_names_are_always_valid():
    name = build_object_name(-89.9999, 179.9999, date(1940, 1, 1), date(1940, 1, 2), FIXED_NOW)
    assert is_valid_object_name(name)


def test_defaults_to_current_utc_time():
    name = build_object_name(0, 0, date(2024, 6, 1), date(2024, 6, 2))
    assert is_valid_object_name(name)


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..%2F..%2Fsecret.json",
        "weather_../../escape_2024-06-01_2024-06-02_20260801T142530Z.json",
        "/absolute/path.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json/../other",
        "",
        "random.json",
        "weather.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.txt",
        "weather_19.0760_72.8777_2024-06-01_2024-06-10.json",
        "WEATHER_19.0760_72.8777_2024-06-01_2024-06-10_20260801T142530Z.json",
    ],
)
def test_rejects_malformed_and_hostile_names(hostile):
    assert not is_valid_object_name(hostile)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.naming'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/naming.py`:

```python
"""Construction and validation of stored object names.

The name a client supplies to GET /weather-file-content/{file} is passed to a
bucket, which makes it a path-traversal surface. Every name is matched against
OBJECT_NAME_PATTERN *before* any storage call, so only names of our own shape
ever reach GCS.
"""

import re
from datetime import date, datetime, timezone

# weather_<lat>_<lon>_<start>_<end>_<timestamp>.json
# Coordinates are always signed-optional with exactly 4 decimal places, which
# is what build_object_name emits.
OBJECT_NAME_PATTERN = re.compile(
    r"^weather_"
    r"(-?\d{1,3}\.\d{4})_"          # latitude
    r"(-?\d{1,3}\.\d{4})_"          # longitude
    r"(\d{4}-\d{2}-\d{2})_"         # start date
    r"(\d{4}-\d{2}-\d{2})_"         # end date
    r"(\d{8}T\d{6}Z)"               # UTC timestamp
    r"\.json$"
)

TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def build_object_name(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    now: datetime | None = None,
) -> str:
    """Return the object name for one stored fetch.

    `now` is injectable so tests can assert an exact string.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime(TIMESTAMP_FORMAT)
    return (
        f"weather_{latitude:.4f}_{longitude:.4f}"
        f"_{start.isoformat()}_{end.isoformat()}_{stamp}.json"
    )


def is_valid_object_name(name: str) -> bool:
    """True only for names this service could itself have generated."""
    return bool(OBJECT_NAME_PATTERN.fullmatch(name))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_naming.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/naming.py backend/tests/test_naming.py
git commit -m "feat(api): add object naming with traversal-safe validation"
```

---

## Task 4: Storage abstraction

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/storage.py`, `backend/app/deps.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Consumes: `app.schemas.StoredFile`, `app.errors.AppError`, `app.config.get_settings`
- Produces:
  - `app.services.storage.StorageClient` — Protocol with `save_json(name, payload) -> None`, `list_files() -> list[StoredFile]`, `get_json(name) -> dict | None`
  - `app.services.storage.InMemoryStorage` — test double; constructor takes no args
  - `app.services.storage.GCSStorage(bucket_name: str, client=None)`
  - `app.deps.get_storage() -> StorageClient`
  - `tests/conftest.py` fixtures: `storage` (InMemoryStorage), `client` (TestClient with `get_storage` overridden)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_storage.py`:

```python
from datetime import datetime, timedelta, timezone

from app.services.storage import InMemoryStorage

PAYLOAD = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}


def test_round_trips_a_payload():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    assert storage.get_json("weather_a.json") == PAYLOAD


def test_missing_file_returns_none():
    assert InMemoryStorage().get_json("nope.json") is None


def test_empty_storage_lists_nothing():
    assert InMemoryStorage().list_files() == []


def test_list_reports_size_in_bytes():
    storage = InMemoryStorage()
    storage.save_json("weather_a.json", PAYLOAD)

    [entry] = storage.list_files()
    assert entry.name == "weather_a.json"
    assert entry.size > 0
    assert entry.created_at.tzinfo is not None


def test_list_is_newest_first():
    storage = InMemoryStorage()
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    storage.save_json("older.json", PAYLOAD, created_at=base)
    storage.save_json("newest.json", PAYLOAD, created_at=base + timedelta(hours=2))
    storage.save_json("middle.json", PAYLOAD, created_at=base + timedelta(hours=1))

    assert [f.name for f in storage.list_files()] == ["newest.json", "middle.json", "older.json"]


def test_stores_bytes_unmodified():
    """The brief says 'full API JSON' — assert nothing is reshaped."""
    storage = InMemoryStorage()
    payload = {"z": 1, "a": {"nested": [1, 2, None]}, "extra_field": "kept"}
    storage.save_json("weather_a.json", payload)

    assert storage.get_json("weather_a.json") == payload
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Create the services package**

```bash
touch backend/app/services/__init__.py
```

- [ ] **Step 4: Write `backend/app/services/storage.py`**

```python
"""Object storage behind a narrow protocol.

Two implementations: GCSStorage for production, InMemoryStorage for tests.
Routes depend on the protocol, never on google.cloud, which is what lets the
whole suite run with no credentials and no network.
"""

import json
from datetime import datetime, timezone
from typing import Protocol

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage as gcs

from app.errors import AppError
from app.schemas import StoredFile


class StorageClient(Protocol):
    """The only storage surface the rest of the app knows about."""

    def save_json(self, name: str, payload: dict) -> None: ...

    def list_files(self) -> list[StoredFile]: ...

    def get_json(self, name: str) -> dict | None:
        """Return the parsed object, or None if it does not exist."""
        ...


class InMemoryStorage:
    """Test double. Mirrors GCSStorage's observable behavior."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, datetime]] = {}

    def save_json(self, name: str, payload: dict, created_at: datetime | None = None) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._objects[name] = (raw, created_at or datetime.now(timezone.utc))

    def list_files(self) -> list[StoredFile]:
        entries = [
            StoredFile(name=name, size=len(raw), created_at=created)
            for name, (raw, created) in self._objects.items()
        ]
        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    def get_json(self, name: str) -> dict | None:
        record = self._objects.get(name)
        return json.loads(record[0]) if record else None


class GCSStorage:
    """Google Cloud Storage implementation.

    Credentials come from Application Default Credentials: the attached
    service account on Cloud Run, or `gcloud auth application-default login`
    locally. No key file is ever read from the repo.
    """

    # Ask GCS for only the three fields we surface. Without this mask the API
    # returns full object metadata for every blob, which is wasted bytes.
    _LIST_FIELDS = "items(name,size,timeCreated),nextPageToken"

    def __init__(self, bucket_name: str, client: gcs.Client | None = None) -> None:
        if not bucket_name:
            raise AppError("GCS_BUCKET is not configured", status_code=500)
        self._bucket_name = bucket_name
        self._client = client or gcs.Client()

    def save_json(self, name: str, payload: dict) -> None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            blob.upload_from_string(
                json.dumps(payload),
                content_type="application/json",
            )
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not write to storage: {exc}", status_code=502) from exc

    def list_files(self) -> list[StoredFile]:
        try:
            blobs = self._client.list_blobs(self._bucket_name, fields=self._LIST_FIELDS)
            entries = [
                StoredFile(
                    name=blob.name,
                    size=blob.size or 0,
                    created_at=blob.time_created,
                )
                for blob in blobs
            ]
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not list storage: {exc}", status_code=502) from exc

        return sorted(entries, key=lambda f: f.created_at, reverse=True)

    def get_json(self, name: str) -> dict | None:
        blob = self._client.bucket(self._bucket_name).blob(name)
        try:
            raw = blob.download_as_bytes()
        except gcp_exceptions.NotFound:
            return None
        except gcp_exceptions.GoogleAPIError as exc:
            raise AppError(f"could not read from storage: {exc}", status_code=502) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError("stored object is not valid JSON", status_code=500) from exc
```

- [ ] **Step 5: Write `backend/app/deps.py`**

```python
"""FastAPI dependency providers.

Keeping this separate is what makes the storage swap a one-line override in
tests: app.dependency_overrides[get_storage] = lambda: InMemoryStorage().
"""

from functools import lru_cache

from app.config import get_settings
from app.services.storage import GCSStorage, StorageClient


@lru_cache
def _gcs_storage() -> GCSStorage:
    """Cached so we build one GCS client per process, not per request."""
    return GCSStorage(get_settings().gcs_bucket)


def get_storage() -> StorageClient:
    return _gcs_storage()
```

- [ ] **Step 6: Write `backend/tests/conftest.py`**

```python
"""Shared fixtures. Every test runs against in-memory storage."""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_storage
from app.main import create_app
from app.services.storage import InMemoryStorage


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    return TestClient(app)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS — storage, naming, schemas, and errors all green

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/ backend/app/deps.py backend/tests/conftest.py backend/tests/test_storage.py
git commit -m "feat(api): add storage protocol with GCS and in-memory implementations"
```

---

## Task 5: Open-Meteo client

**Files:**
- Create: `backend/app/services/open_meteo.py`
- Test: `backend/tests/test_open_meteo.py`

**Interfaces:**
- Consumes: `app.errors.AppError`, `app.config.get_settings`
- Produces:
  - `app.services.open_meteo.DAILY_VARIABLES: list[str]`
  - `app.services.open_meteo.fetch_daily_history(latitude, longitude, start_date, end_date) -> dict` (async)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_open_meteo.py`:

```python
from datetime import date

import httpx
import pytest
import respx

from app.errors import AppError
from app.services.open_meteo import DAILY_VARIABLES, fetch_daily_history

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

SAMPLE = {
    "latitude": 19.125,
    "longitude": 72.875,
    "daily_units": {"temperature_2m_max": "°C"},
    "daily": {
        "time": ["2024-06-01", "2024-06-02"],
        "temperature_2m_max": [34.4, 31.6],
        "temperature_2m_min": [28.1, 27.0],
        "apparent_temperature_max": [40.2, 37.1],
        "apparent_temperature_min": [31.0, 30.2],
    },
}

ARGS = (19.076, 72.8777, date(2024, 6, 1), date(2024, 6, 2))


@respx.mock
@pytest.mark.asyncio
async def test_requests_all_four_required_variables():
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    await fetch_daily_history(*ARGS)

    requested = route.calls.last.request.url.params["daily"].split(",")
    assert set(requested) == {
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "apparent_temperature_min",
    }
    assert set(DAILY_VARIABLES) == set(requested)


@respx.mock
@pytest.mark.asyncio
async def test_sends_the_correct_query_parameters():
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    await fetch_daily_history(*ARGS)

    params = route.calls.last.request.url.params
    assert params["latitude"] == "19.076"
    assert params["longitude"] == "72.8777"
    assert params["start_date"] == "2024-06-01"
    assert params["end_date"] == "2024-06-02"
    assert params["timezone"] == "auto"


@respx.mock
@pytest.mark.asyncio
async def test_returns_the_body_unmodified():
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    assert await fetch_daily_history(*ARGS) == SAMPLE


@respx.mock
@pytest.mark.asyncio
async def test_upstream_400_surfaces_the_reason_as_400():
    respx.get(ARCHIVE).mock(
        return_value=httpx.Response(
            400, json={"error": True, "reason": "Parameter 'end_date' is out of allowed range"}
        )
    )

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 400
    assert "out of allowed range" in caught.value.message


@respx.mock
@pytest.mark.asyncio
async def test_upstream_500_becomes_502():
    respx.get(ARCHIVE).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 502
    assert "Open-Meteo" in caught.value.message


@respx.mock
@pytest.mark.asyncio
async def test_timeout_becomes_502():
    respx.get(ARCHIVE).mock(side_effect=httpx.ConnectTimeout("timed out"))

    with pytest.raises(AppError) as caught:
        await fetch_daily_history(*ARGS)

    assert caught.value.status_code == 502
    assert "Open-Meteo" in caught.value.message
```

- [ ] **Step 2: Add the async test dependency**

Append to `backend/requirements.txt`:

```
pytest-asyncio==1.3.0
```

Install and configure. Replace `backend/pytest.ini` with:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning
```

```bash
cd backend && .venv/Scripts/python.exe -m pip install -r requirements.txt
```

> With `asyncio_mode = auto`, the `@pytest.mark.asyncio` decorators above are redundant but harmless — leave them in as documentation.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_open_meteo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.open_meteo'`

- [ ] **Step 4: Write the implementation**

Create `backend/app/services/open_meteo.py`:

```python
"""Client for the Open-Meteo historical archive API.

This is the only place in the app that talks to Open-Meteo. The browser never
does — it only ever reads files we already stored.
"""

import logging
from datetime import date

import httpx

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

# The four the brief requires. Kept as a module constant so the test can assert
# on the exact set rather than a hand-copied string.
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
]

TIMEOUT_SECONDS = 30.0
RETRIES = 1


async def fetch_daily_history(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> dict:
    """Return Open-Meteo's response body verbatim.

    Raises AppError(400) when Open-Meteo rejects the request, AppError(502)
    when it is unreachable or failing.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "auto",
    }

    transport = httpx.AsyncHTTPTransport(retries=RETRIES)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.get(get_settings().open_meteo_url, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Open-Meteo unreachable: %s", exc)
        raise AppError(f"Open-Meteo is unreachable: {exc}", status_code=502) from exc

    if response.status_code == 400:
        # Open-Meteo explains its own rejections well; pass the reason through
        # rather than inventing our own wording.
        reason = _reason(response) or "Open-Meteo rejected the request"
        raise AppError(reason, status_code=400)

    if response.status_code >= 500 or response.status_code != 200:
        raise AppError(
            f"Open-Meteo returned an unexpected status {response.status_code}",
            status_code=502,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise AppError("Open-Meteo returned a malformed response", status_code=502) from exc


def _reason(response: httpx.Response) -> str | None:
    try:
        return response.json().get("reason")
    except ValueError:
        return None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_open_meteo.py -v`
Expected: PASS — 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/open_meteo.py backend/tests/test_open_meteo.py backend/requirements.txt backend/pytest.ini
git commit -m "feat(api): add Open-Meteo archive client with upstream error mapping"
```

---

## Task 6: POST /store-weather-data

**Files:**
- Create: `backend/app/routes/__init__.py`, `backend/app/routes/weather.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routes.py`

**Interfaces:**
- Consumes: `StoreWeatherRequest`, `StoreWeatherResponse`, `build_object_name`, `fetch_daily_history`, `get_storage`
- Produces: `app.routes.weather.router` (an `APIRouter`), mounted in `create_app()`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_routes.py`:

```python
import httpx
import respx

from app.naming import is_valid_object_name

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

SAMPLE = {
    "latitude": 19.125,
    "longitude": 72.875,
    "daily_units": {"temperature_2m_max": "°C"},
    "daily": {
        "time": ["2024-06-01", "2024-06-02"],
        "temperature_2m_max": [34.4, 31.6],
        "temperature_2m_min": [28.1, 27.0],
        "apparent_temperature_max": [40.2, 37.1],
        "apparent_temperature_min": [31.0, 30.2],
    },
}

VALID = {
    "latitude": 19.076,
    "longitude": 72.8777,
    "start_date": "2024-06-01",
    "end_date": "2024-06-02",
}


@respx.mock
def test_store_returns_ok_and_a_wellformed_filename(client):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    response = client.post("/store-weather-data", json=VALID)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert is_valid_object_name(body["file"])
    assert body["file"].startswith("weather_19.0760_72.8777_2024-06-01_2024-06-02_")


@respx.mock
def test_store_persists_the_api_json_unmodified(client, storage):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]

    assert storage.get_json(name) == SAMPLE


@respx.mock
def test_store_rejects_invalid_input_before_calling_open_meteo(client):
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    response = client.post("/store-weather-data", json={**VALID, "latitude": 91})

    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert "latitude" in response.json()["message"]
    assert not route.called, "must not spend an upstream call on input we know is invalid"


@respx.mock
def test_store_rejects_a_32_day_range(client):
    response = client.post(
        "/store-weather-data",
        json={**VALID, "start_date": "2024-06-01", "end_date": "2024-07-02"},
    )

    assert response.status_code == 400
    assert "31 days" in response.json()["message"]


@respx.mock
def test_store_maps_upstream_failure_to_502(client):
    respx.get(ARCHIVE).mock(return_value=httpx.Response(503, text="unavailable"))

    response = client.post("/store-weather-data", json=VALID)

    assert response.status_code == 502
    assert response.json()["status"] == "error"
    assert "Open-Meteo" in response.json()["message"]


def test_store_rejects_a_non_json_body(client):
    response = client.post(
        "/store-weather-data",
        content="not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_routes.py -v`
Expected: FAIL — 404 on `/store-weather-data`, since no route exists yet

- [ ] **Step 3: Create the routes package**

```bash
touch backend/app/routes/__init__.py
```

- [ ] **Step 4: Write `backend/app/routes/weather.py`**

```python
"""The three weather endpoints.

Routes stay thin: they translate HTTP to service calls and back. Validation
lives in schemas.py, I/O in services/, naming in naming.py.
"""

from fastapi import APIRouter, Depends

from app.deps import get_storage
from app.naming import build_object_name
from app.schemas import StoreWeatherRequest, StoreWeatherResponse
from app.services.open_meteo import fetch_daily_history
from app.services.storage import StorageClient

router = APIRouter(tags=["weather"])


@router.post("/store-weather-data", response_model=StoreWeatherResponse)
async def store_weather_data(
    request: StoreWeatherRequest,
    storage: StorageClient = Depends(get_storage),
) -> StoreWeatherResponse:
    """Fetch a date range from Open-Meteo and persist the raw response."""
    # FastAPI has already validated `request` — an invalid payload never gets
    # here, so we never spend an upstream call on input we know is bad.
    payload = await fetch_daily_history(
        request.latitude,
        request.longitude,
        request.start_date,
        request.end_date,
    )

    name = build_object_name(
        request.latitude,
        request.longitude,
        request.start_date,
        request.end_date,
    )
    storage.save_json(name, payload)

    return StoreWeatherResponse(status="ok", file=name)
```

- [ ] **Step 5: Mount the router — modify `backend/app/main.py`**

Replace the body of `create_app()` so it includes the router. The full file becomes:

```python
"""Application factory."""

from fastapi import FastAPI

from app.errors import register_error_handlers
from app.routes import weather


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Explorer API",
        description="Fetches historical daily weather from Open-Meteo and stores it in GCS.",
        version="1.0.0",
    )

    register_error_handlers(app)
    app.include_router(weather.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS — all suites green

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/ backend/app/main.py backend/tests/test_routes.py
git commit -m "feat(api): add POST /store-weather-data"
```

---

## Task 7: GET /list-weather-files

**Files:**
- Modify: `backend/app/routes/weather.py`
- Modify: `backend/tests/test_routes.py`

**Interfaces:**
- Consumes: `ListFilesResponse`, `StoredFile`, `get_storage`
- Produces: `GET /list-weather-files` returning `{"files": [{"name", "size", "created_at"}]}`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_routes.py`:

```python
from datetime import datetime, timedelta, timezone


def test_list_is_empty_for_a_fresh_bucket(client):
    response = client.get("/list-weather-files")

    assert response.status_code == 200
    assert response.json() == {"files": []}


def test_list_returns_name_size_and_created_at(client, storage):
    storage.save_json("weather_a.json", {"daily": {"time": ["2024-06-01"]}})

    response = client.get("/list-weather-files")

    assert response.status_code == 200
    [entry] = response.json()["files"]
    assert entry["name"] == "weather_a.json"
    assert isinstance(entry["size"], int) and entry["size"] > 0
    # Must parse as ISO 8601.
    datetime.fromisoformat(entry["created_at"])


def test_list_is_ordered_newest_first(client, storage):
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    storage.save_json("older.json", {"a": 1}, created_at=base)
    storage.save_json("newest.json", {"a": 1}, created_at=base + timedelta(hours=2))
    storage.save_json("middle.json", {"a": 1}, created_at=base + timedelta(hours=1))

    names = [f["name"] for f in client.get("/list-weather-files").json()["files"]]

    assert names == ["newest.json", "middle.json", "older.json"]


@respx.mock
def test_a_stored_file_appears_in_the_listing(client):
    """End-to-end within the backend: store then list."""
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]
    names = [f["name"] for f in client.get("/list-weather-files").json()["files"]]

    assert name in names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_routes.py -k list -v`
Expected: FAIL — 404, route not defined

- [ ] **Step 3: Add the route — append to `backend/app/routes/weather.py`**

Add the import at the top (alongside the existing schema imports):

```python
from app.schemas import ListFilesResponse, StoreWeatherRequest, StoreWeatherResponse
```

Then append this handler to the file:

```python
@router.get("/list-weather-files", response_model=ListFilesResponse)
async def list_weather_files(
    storage: StorageClient = Depends(get_storage),
) -> ListFilesResponse:
    """List stored objects, newest first.

    One SDK call with a field mask — no per-object metadata fetches.
    """
    return ListFilesResponse(files=storage.list_files())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/weather.py backend/tests/test_routes.py
git commit -m "feat(api): add GET /list-weather-files"
```

---

## Task 8: GET /weather-file-content/{file}

**Files:**
- Modify: `backend/app/routes/weather.py`
- Modify: `backend/tests/test_routes.py`

**Interfaces:**
- Consumes: `is_valid_object_name`, `AppError`, `get_storage`
- Produces: `GET /weather-file-content/{file}` returning the stored JSON, or 404 `{"status": "error", "message": "not found"}`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_routes.py`:

> Tasks 6-8 each append to this file. Move every `import` line to the top of
> the file as you go — mid-file imports are legal Python but read badly.

```python
import pytest

NOT_FOUND = {"status": "error", "message": "not found"}


def test_content_round_trips_stored_json(client, storage):
    payload = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [34.4]}}
    name = "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.json"
    storage.save_json(name, payload)

    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 200
    assert response.json() == payload


def test_content_returns_404_for_a_missing_file(client):
    name = "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.json"

    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


@pytest.mark.parametrize(
    "hostile",
    [
        "..%2F..%2Fetc%2Fpasswd",
        "random.json",
        "weather.json",
        "weather_19.0760_72.8777_2024-06-01_2024-06-02_20260801T142530Z.txt",
    ],
)
def test_content_returns_404_for_invalid_names(client, hostile):
    """Malformed and missing are deliberately indistinguishable — it leaks nothing."""
    response = client.get(f"/weather-file-content/{hostile}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


def test_invalid_name_never_reaches_storage(client, monkeypatch, storage):
    def explode(_name):
        raise AssertionError("storage must not be queried for an invalid name")

    monkeypatch.setattr(storage, "get_json", explode)

    response = client.get("/weather-file-content/not-our-shape.json")

    assert response.status_code == 404


@respx.mock
def test_store_then_read_back(client):
    """Full backend round trip: store -> list -> read."""
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=SAMPLE))

    name = client.post("/store-weather-data", json=VALID).json()["file"]
    response = client.get(f"/weather-file-content/{name}")

    assert response.status_code == 200
    assert response.json() == SAMPLE
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_routes.py -k content -v`
Expected: FAIL — 404 from the router with the wrong body, or route missing

- [ ] **Step 3: Add the route — append to `backend/app/routes/weather.py`**

Add to the imports at the top:

```python
from app.errors import AppError
from app.naming import build_object_name, is_valid_object_name
```

Then append:

```python
@router.get("/weather-file-content/{file}")
async def weather_file_content(
    file: str,
    storage: StorageClient = Depends(get_storage),
) -> dict:
    """Return one stored object's JSON.

    The name is checked against our own pattern before any storage call, so a
    traversal attempt never reaches the bucket. Malformed and missing names
    return the identical 404 — distinguishing them would leak bucket contents.
    """
    if not is_valid_object_name(file):
        raise AppError("not found", status_code=404)

    payload = storage.get_json(file)
    if payload is None:
        raise AppError("not found", status_code=404)

    return payload
```

- [ ] **Step 4: Run the whole suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS — every backend test green

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/weather.py backend/tests/test_routes.py
git commit -m "feat(api): add GET /weather-file-content with traversal defense"
```

---

## Task 9: CORS, Dockerfile, and local smoke test

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/Dockerfile`, `backend/.dockerignore`, `backend/.env.example`
- Test: `backend/tests/test_cors.py`

**Interfaces:**
- Consumes: `get_settings().origin_list`
- Produces: a container that serves the app on `$PORT`; CORS headers on cross-origin requests

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_cors.py`:

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_allowed_origin_receives_cors_headers():
    # The default allowed origin is the Vite dev server, so no env setup here.
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_permits_post():
    client = TestClient(create_app())
    response = client.options(
        "/store-weather-data",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code in (200, 204)
    assert "POST" in response.headers["access-control-allow-methods"]


def test_origin_list_splits_and_trims():
    settings = Settings(allowed_origins="http://a.com, https://b.com ,")
    assert settings.origin_list == ["http://a.com", "https://b.com"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cors.py -v`
Expected: FAIL — `KeyError: 'access-control-allow-origin'`

- [ ] **Step 3: Add CORS — modify `backend/app/main.py`**

Add these imports:

```python
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
```

And insert this inside `create_app()`, immediately after the `FastAPI(...)` construction:

```python
    # An explicit allowlist, not "*". The frontend origin is injected at deploy
    # time via ALLOWED_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().origin_list,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cors.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Create `backend/.env.example`**

```
# Name of the GCS bucket that holds stored weather files.
GCS_BUCKET=your-bucket-name

# Comma-separated origins allowed by CORS.
ALLOWED_ORIGINS=http://localhost:5173
```

- [ ] **Step 6: Create `backend/.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
tests/
.env
```

- [ ] **Step 7: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first so layer caching survives source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run injects PORT and expects the container to listen on it.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

- [ ] **Step 8: Run the full suite and a local smoke test**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -v
```
Expected: every test passes.

Then start the server and confirm it responds:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

```bash
curl -X POST http://localhost:8000/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":19.076,"longitude":72.8777,"start_date":"2024-06-01","end_date":"2024-06-10"}'
```
Expected: `{"status":"error","message":"GCS_BUCKET is not configured"}` with status 500 — correct, since no bucket exists yet. This confirms validation passed and the storage layer failed loudly rather than silently.

```bash
curl -X POST http://localhost:8000/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":999,"longitude":0,"start_date":"2024-06-01","end_date":"2024-06-10"}'
```
Expected: HTTP 400, `{"status":"error","message":"latitude: Input should be less than or equal to 90"}`

Stop the server with Ctrl-C.

- [ ] **Step 9: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore backend/.env.example backend/app/main.py backend/tests/test_cors.py
git commit -m "feat(api): enable CORS and containerize for Cloud Run"
```

---

## Task 10: Frontend scaffold, types, and API client

**Files:**
- Create: `frontend/` (via create-vite), `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/types.ts`, `frontend/src/api/client.ts`, `frontend/.env.example`
- Test: manual build verification

**Interfaces:**
- Consumes: the backend's three endpoints
- Produces:
  - `types.ts`: `StoredFileMeta`, `WeatherPayload`, `StoreRequest`, `StoreResponse`
  - `api/client.ts`: `storeWeatherData(req)`, `listWeatherFiles()`, `getWeatherFileContent(name)`, `ApiError`

- [ ] **Step 1: Scaffold the project**

From the repo root:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite recharts
```

> Verified 2026-08-01: this produces React 19.2, Vite 8.2, TypeScript ~6.0, and pulls Tailwind 4.3.3 and Recharts 3.10.1.

- [ ] **Step 2: Configure Tailwind 4**

Replace `frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Replace the entire contents of `frontend/src/index.css` with one line:

```css
@import "tailwindcss";
```

> Tailwind 4 needs no `tailwind.config.js` and no `postcss.config.js`. Do not create them.

Delete `frontend/src/App.css` — the template's styles are not used:

```bash
rm frontend/src/App.css
```

- [ ] **Step 3: Create `frontend/.env.example`**

```
# Base URL of the backend. No trailing slash.
VITE_API_BASE=http://localhost:8000
```

Also create `frontend/.env.local` with the same content so local dev works immediately.

- [ ] **Step 4: Create `frontend/src/types.ts`**

```ts
/** Shapes exchanged with the backend. Mirrors backend/app/schemas.py. */

export interface StoredFileMeta {
  name: string
  size: number // bytes
  created_at: string // ISO 8601
}

/** The Open-Meteo archive response, stored verbatim.
 *  `daily` is columnar: parallel arrays indexed by day. */
export interface WeatherPayload {
  latitude?: number
  longitude?: number
  timezone?: string
  elevation?: number
  daily_units?: Record<string, string>
  daily?: {
    time: string[]
    temperature_2m_max?: (number | null)[]
    temperature_2m_min?: (number | null)[]
    apparent_temperature_max?: (number | null)[]
    apparent_temperature_min?: (number | null)[]
  }
}

export interface StoreRequest {
  latitude: number
  longitude: number
  start_date: string
  end_date: string
}

export interface StoreResponse {
  status: string
  file: string
}
```

- [ ] **Step 5: Create `frontend/src/api/client.ts`**

```ts
/** The only module that knows the backend exists.
 *  Every failure arrives as an ApiError carrying the backend's message. */

import type {
  StoreRequest,
  StoreResponse,
  StoredFileMeta,
  WeatherPayload,
} from '../types'

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    // fetch only rejects on network-level failure, never on 4xx/5xx.
    throw new ApiError('Cannot reach the API. Is the backend running?', 0)
  }

  if (!response.ok) {
    // The backend guarantees {"status","message"} on every error.
    const message = await response
      .json()
      .then((body) => body?.message ?? response.statusText)
      .catch(() => response.statusText)
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export function storeWeatherData(payload: StoreRequest): Promise<StoreResponse> {
  return request<StoreResponse>('/store-weather-data', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listWeatherFiles(): Promise<StoredFileMeta[]> {
  return request<{ files: StoredFileMeta[] }>('/list-weather-files').then((r) => r.files)
}

export function getWeatherFileContent(name: string): Promise<WeatherPayload> {
  return request<WeatherPayload>(`/weather-file-content/${encodeURIComponent(name)}`)
}
```

- [ ] **Step 6: Verify the build**

Replace `frontend/src/App.tsx` with a placeholder that proves Tailwind is active:

```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <h1 className="text-3xl font-bold text-slate-800">Weather Explorer</h1>
    </div>
  )
}
```

Run: `cd frontend && npm run build`
Expected: build succeeds; `dist/assets/*.css` exists and is non-empty (Tailwind emitted styles).

Run: `npm run dev` and open the URL — the heading should be bold, dark slate, on a light grey page. Stop with Ctrl-C.

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat(ui): scaffold Vite React app with Tailwind 4 and typed API client"
```

---

## Task 11: Pure transforms

**Files:**
- Create: `frontend/src/lib/transform.ts`, `frontend/src/lib/transform.test.ts`
- Modify: `frontend/package.json` (add vitest)

**Interfaces:**
- Consumes: `WeatherPayload` from `types.ts`
- Produces:
  - `toDailyRows(payload: WeatherPayload): DailyRow[]`
  - `DailyRow` — `{ date: string; tempMax: number | null; tempMin: number | null; feelsMax: number | null; feelsMin: number | null }`
  - `paginate<T>(rows: T[], page: number, pageSize: number): T[]`
  - `pageCount(total: number, pageSize: number): number`
  - `clampPage(page: number, total: number, pageSize: number): number`
  - `validateInputs(values): string | null`

- [ ] **Step 1: Install the test runner**

```bash
cd frontend && npm install -D vitest
```

Add to `frontend/package.json` under `"scripts"`:

```json
"test": "vitest run"
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/transform.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import {
  clampPage,
  pageCount,
  paginate,
  toDailyRows,
  validateInputs,
} from './transform'
import type { WeatherPayload } from '../types'

const PAYLOAD: WeatherPayload = {
  daily: {
    time: ['2024-06-01', '2024-06-02', '2024-06-03'],
    temperature_2m_max: [34.4, 31.6, null],
    temperature_2m_min: [28.1, 27.0, 26.2],
    apparent_temperature_max: [40.2, 37.1, 36.0],
    apparent_temperature_min: [31.0, 30.2, 29.8],
  },
}

describe('toDailyRows', () => {
  it('zips the columnar payload into one row per day', () => {
    const rows = toDailyRows(PAYLOAD)

    expect(rows).toHaveLength(3)
    expect(rows[0]).toEqual({
      date: '2024-06-01',
      tempMax: 34.4,
      tempMin: 28.1,
      feelsMax: 40.2,
      feelsMin: 31.0,
    })
  })

  it('keeps rows that have null readings rather than dropping them', () => {
    const rows = toDailyRows(PAYLOAD)

    expect(rows).toHaveLength(3)
    expect(rows[2].tempMax).toBeNull()
    expect(rows[2].tempMin).toBe(26.2)
  })

  it('returns an empty array for a payload with no daily block', () => {
    expect(toDailyRows({})).toEqual([])
    expect(toDailyRows({ daily: { time: [] } })).toEqual([])
  })

  it('tolerates a missing variable array', () => {
    const rows = toDailyRows({ daily: { time: ['2024-06-01'] } })

    expect(rows[0].tempMax).toBeNull()
    expect(rows[0].feelsMin).toBeNull()
  })
})

describe('paginate', () => {
  const rows = Array.from({ length: 25 }, (_, i) => i)

  it('returns the first page', () => {
    expect(paginate(rows, 1, 10)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
  })

  it('returns a partial final page', () => {
    expect(paginate(rows, 3, 10)).toEqual([20, 21, 22, 23, 24])
  })

  it('returns nothing past the end', () => {
    expect(paginate(rows, 9, 10)).toEqual([])
  })

  it('handles an empty input', () => {
    expect(paginate([], 1, 10)).toEqual([])
  })
})

describe('pageCount', () => {
  it.each([
    [0, 10, 1],
    [1, 10, 1],
    [10, 10, 1],
    [11, 10, 2],
    [25, 10, 3],
    [25, 50, 1],
  ])('pageCount(%i, %i) === %i', (total, size, expected) => {
    expect(pageCount(total, size)).toBe(expected)
  })
})

describe('clampPage', () => {
  it('pulls an out-of-range page back to the last page', () => {
    // Reproduces the real bug: viewing page 3 of 25 rows, then switching
    // page size to 50 leaves only 1 page.
    expect(clampPage(3, 25, 50)).toBe(1)
  })

  it('leaves a valid page alone', () => {
    expect(clampPage(2, 25, 10)).toBe(2)
  })

  it('never returns less than 1', () => {
    expect(clampPage(0, 0, 10)).toBe(1)
  })
})

describe('validateInputs', () => {
  const VALID = {
    latitude: '19.076',
    longitude: '72.8777',
    startDate: '2024-06-01',
    endDate: '2024-06-10',
  }

  it('accepts valid input', () => {
    expect(validateInputs(VALID)).toBeNull()
  })

  it.each([
    [{ latitude: '' }, 'Latitude'],
    [{ latitude: 'abc' }, 'Latitude'],
    [{ latitude: '91' }, 'Latitude'],
    [{ longitude: '181' }, 'Longitude'],
    [{ startDate: '' }, 'date'],
    [{ startDate: '2024-06-11' }, 'on or before'],
    [{ endDate: '2024-07-02' }, '31 days'],
  ])('rejects %o', (patch, fragment) => {
    const message = validateInputs({ ...VALID, ...patch })
    expect(message).toContain(fragment)
  })

  it('accepts exactly 31 inclusive days, matching the backend', () => {
    expect(
      validateInputs({ ...VALID, startDate: '2024-06-01', endDate: '2024-07-01' }),
    ).toBeNull()
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot resolve `./transform`

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/transform.ts`:

```ts
/** Pure functions only — no React, no fetch.
 *  Everything the chart and table render is derived from the loaded file
 *  through these, so there is never a second copy of the data to drift. */

import type { WeatherPayload } from '../types'

export interface DailyRow {
  date: string
  tempMax: number | null
  tempMin: number | null
  feelsMax: number | null
  feelsMin: number | null
}

/** Open-Meteo returns columnar arrays; the UI wants one object per day. */
export function toDailyRows(payload: WeatherPayload): DailyRow[] {
  const daily = payload.daily
  if (!daily?.time?.length) return []

  const at = (values: (number | null)[] | undefined, i: number): number | null =>
    values?.[i] ?? null

  return daily.time.map((date, i) => ({
    date,
    tempMax: at(daily.temperature_2m_max, i),
    tempMin: at(daily.temperature_2m_min, i),
    feelsMax: at(daily.apparent_temperature_max, i),
    feelsMin: at(daily.apparent_temperature_min, i),
  }))
}

export function paginate<T>(rows: T[], page: number, pageSize: number): T[] {
  const start = (page - 1) * pageSize
  return rows.slice(start, start + pageSize)
}

/** Always at least 1, so the UI can render "Page 1 of 1" for an empty table. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize))
}

/** Keeps the current page in range after the row count or page size changes. */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(1, page), pageCount(total, pageSize))
}

export interface InputValues {
  latitude: string
  longitude: string
  startDate: string
  endDate: string
}

const MAX_RANGE_DAYS = 31
const MS_PER_DAY = 86_400_000

/** Mirrors backend/app/schemas.py so obvious mistakes cost no round trip.
 *  The server stays the authority — this is a convenience, not a guarantee. */
export function validateInputs(values: InputValues): string | null {
  const latitude = Number(values.latitude)
  const longitude = Number(values.longitude)

  if (values.latitude.trim() === '' || Number.isNaN(latitude)) {
    return 'Latitude must be a number.'
  }
  if (latitude < -90 || latitude > 90) {
    return 'Latitude must be between -90 and 90.'
  }
  if (values.longitude.trim() === '' || Number.isNaN(longitude)) {
    return 'Longitude must be a number.'
  }
  if (longitude < -180 || longitude > 180) {
    return 'Longitude must be between -180 and 180.'
  }
  if (!values.startDate || !values.endDate) {
    return 'Both a start date and an end date are required.'
  }

  const start = new Date(values.startDate)
  const end = new Date(values.endDate)
  if (Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf())) {
    return 'Dates must be valid calendar dates.'
  }
  if (start > end) {
    return 'Start date must be on or before end date.'
  }

  // Inclusive day count, matching the backend's rule exactly.
  const days = Math.round((end.valueOf() - start.valueOf()) / MS_PER_DAY) + 1
  if (days > MAX_RANGE_DAYS) {
    return `Date range must not exceed ${MAX_RANGE_DAYS} days (requested ${days}).`
  }
  if (end > new Date()) {
    return 'End date must not be in the future.'
  }

  return null
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — all transform tests green

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/ frontend/package.json frontend/package-lock.json
git commit -m "test(ui): add pure transforms for rows, pagination, and validation"
```

---

## Task 12: Input panel

**Files:**
- Create: `frontend/src/components/StatusBanner.tsx`, `frontend/src/components/InputPanel.tsx`, `frontend/src/hooks/useAsync.ts`

**Interfaces:**
- Consumes: `storeWeatherData`, `ApiError`, `validateInputs`, `InputValues`
- Produces:
  - `useAsync<T>()` → `{ run, loading, error }`
  - `<StatusBanner kind="error" | "success" | "info" message={string} />`
  - `<InputPanel onStored={(filename: string) => void} />`

- [ ] **Step 1: Create `frontend/src/hooks/useAsync.ts`**

```ts
/** Wraps one async action with its own loading and error state.
 *  Each panel owns an instance, so a failure in one never blanks another. */

import { useCallback, useState } from 'react'

import { ApiError } from '../api/client'

export function useAsync<Args extends unknown[], T>(
  action: (...args: Args) => Promise<T>,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(
    async (...args: Args): Promise<T | null> => {
      setLoading(true)
      setError(null)
      try {
        return await action(...args)
      } catch (caught) {
        const message =
          caught instanceof ApiError ? caught.message : 'Something went wrong.'
        setError(message)
        return null
      } finally {
        setLoading(false)
      }
    },
    [action],
  )

  return { run, loading, error }
}
```

- [ ] **Step 2: Create `frontend/src/components/StatusBanner.tsx`**

```tsx
type Kind = 'error' | 'success' | 'info'

const STYLES: Record<Kind, string> = {
  error: 'bg-red-50 text-red-800 border-red-200',
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  info: 'bg-slate-50 text-slate-700 border-slate-200',
}

export function StatusBanner({ kind, message }: { kind: Kind; message: string }) {
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={`rounded-md border px-3 py-2 text-sm break-words ${STYLES[kind]}`}
    >
      {message}
    </div>
  )
}
```

- [ ] **Step 3: Create `frontend/src/components/InputPanel.tsx`**

```tsx
import { useState, type ChangeEvent, type FormEvent } from 'react'

import { storeWeatherData } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { validateInputs, type InputValues } from '../lib/transform'
import { StatusBanner } from './StatusBanner'

const PRESETS = [
  { label: 'Mumbai', latitude: '19.0760', longitude: '72.8777' },
  { label: 'London', latitude: '51.5072', longitude: '-0.1276' },
  { label: 'New York', latitude: '40.7128', longitude: '-74.0060' },
  { label: 'Sydney', latitude: '-33.8688', longitude: '151.2093' },
]

/** Default to a fully-available 7-day window: Open-Meteo's archive lags
 *  roughly two days, so we end three days back and stay clear of it. */
function defaultRange() {
  const end = new Date()
  end.setDate(end.getDate() - 3)
  const start = new Date(end)
  start.setDate(start.getDate() - 6)
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  return { startDate: iso(start), endDate: iso(end) }
}

const FIELD =
  'w-full rounded-md border border-slate-300 px-3 py-2 text-sm ' +
  'focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500'

export function InputPanel({ onStored }: { onStored: (filename: string) => void }) {
  const [values, setValues] = useState<InputValues>({
    latitude: '19.0760',
    longitude: '72.8777',
    ...defaultRange(),
  })
  const [localError, setLocalError] = useState<string | null>(null)
  const [storedFile, setStoredFile] = useState<string | null>(null)

  const store = useAsync(storeWeatherData)

  // Explicit type-only imports: `React.ChangeEvent` would rely on the UMD
  // global, which TypeScript rejects inside a module under the modern JSX
  // transform the Vite template configures.
  const set = (key: keyof InputValues) => (event: ChangeEvent<HTMLInputElement>) =>
    setValues((previous) => ({ ...previous, [key]: event.target.value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    setStoredFile(null)

    // Catch the obvious mistakes here so they cost no round trip.
    const problem = validateInputs(values)
    setLocalError(problem)
    if (problem) return

    const result = await store.run({
      latitude: Number(values.latitude),
      longitude: Number(values.longitude),
      start_date: values.startDate,
      end_date: values.endDate,
    })

    if (result) {
      setStoredFile(result.file)
      onStored(result.file)
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Fetch &amp; store</h2>

      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Latitude</span>
            <input
              className={FIELD}
              value={values.latitude}
              onChange={set('latitude')}
              inputMode="decimal"
              placeholder="-90 to 90"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Longitude</span>
            <input
              className={FIELD}
              value={values.longitude}
              onChange={set('longitude')}
              inputMode="decimal"
              placeholder="-180 to 180"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">Start date</span>
            <input className={FIELD} type="date" value={values.startDate} onChange={set('startDate')} />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-600">End date</span>
            <input className={FIELD} type="date" value={values.endDate} onChange={set('endDate')} />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() =>
                setValues((previous) => ({
                  ...previous,
                  latitude: preset.latitude,
                  longitude: preset.longitude,
                }))
              }
              className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
            >
              {preset.label}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={store.loading}
          className="w-full rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400 sm:w-auto"
        >
          {store.loading ? 'Fetching…' : 'Fetch & store data'}
        </button>

        <p className="text-xs text-slate-500">Maximum range is 31 days.</p>

        {localError && <StatusBanner kind="error" message={localError} />}
        {store.error && <StatusBanner kind="error" message={store.error} />}
        {storedFile && <StatusBanner kind="success" message={`Stored as ${storedFile}`} />}
      </form>
    </section>
  )
}
```

- [ ] **Step 4: Verify it compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ frontend/src/hooks/
git commit -m "feat(ui): add input panel with client-side validation and presets"
```

---

## Task 13: File list

**Files:**
- Create: `frontend/src/components/FileList.tsx`

**Interfaces:**
- Consumes: `listWeatherFiles`, `StoredFileMeta`, `useAsync`, `StatusBanner`
- Produces: `<FileList files, loading, error, selectedName, onSelect, onRefresh />` — a controlled component; `App` owns the data so it can refresh after a store

- [ ] **Step 1: Create `frontend/src/components/FileList.tsx`**

```tsx
import type { StoredFileMeta } from '../types'
import { StatusBanner } from './StatusBanner'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.valueOf()) ? iso : parsed.toLocaleString()
}

interface Props {
  files: StoredFileMeta[]
  loading: boolean
  error: string | null
  selectedName: string | null
  onSelect: (name: string) => void
  onRefresh: () => void
}

export function FileList({
  files,
  loading,
  error,
  selectedName,
  onSelect,
  onRefresh,
}: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-800">Stored files</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? 'Loading…' : 'Browse'}
        </button>
      </div>

      {error && <StatusBanner kind="error" message={error} />}

      {!error && !loading && files.length === 0 && (
        <StatusBanner kind="info" message="No files stored yet. Fetch some data to get started." />
      )}

      {files.length > 0 && (
        <ul className="max-h-96 space-y-1 overflow-y-auto">
          {files.map((file) => {
            const selected = file.name === selectedName
            return (
              <li key={file.name}>
                <button
                  type="button"
                  onClick={() => onSelect(file.name)}
                  aria-current={selected}
                  className={`w-full rounded-md border px-3 py-2 text-left transition ${
                    selected
                      ? 'border-sky-300 bg-sky-50'
                      : 'border-transparent hover:bg-slate-50'
                  }`}
                >
                  <span className="block truncate font-mono text-xs text-slate-700">
                    {file.name}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {formatSize(file.size)} · {formatDate(file.created_at)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FileList.tsx
git commit -m "feat(ui): add stored file browser with metadata"
```

---

## Task 14: Chart and paginated table

**Files:**
- Create: `frontend/src/components/TempChart.tsx`, `frontend/src/components/DataTable.tsx`

**Interfaces:**
- Consumes: `DailyRow`, `paginate`, `pageCount`, `clampPage`
- Produces: `<TempChart rows={DailyRow[]} />`, `<DataTable rows={DailyRow[]} />`

- [ ] **Step 1: Create `frontend/src/components/TempChart.tsx`**

```tsx
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DailyRow } from '../lib/transform'

const SERIES = [
  { key: 'tempMax', name: 'Max temp', color: '#dc2626' },
  { key: 'tempMin', name: 'Min temp', color: '#2563eb' },
  { key: 'feelsMax', name: 'Feels-like max', color: '#f97316' },
  { key: 'feelsMin', name: 'Feels-like min', color: '#0891b2' },
] as const

export function TempChart({ rows }: { rows: DailyRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-slate-500">
        No daily data in this file.
      </p>
    )
  }

  return (
    <div className="h-72 w-full sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" unit="°" width={48} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            formatter={(value) => (value === null ? '—' : `${value}°C`)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {SERIES.map((series) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
              name={series.name}
              stroke={series.color}
              dot={false}
              strokeWidth={2}
              // Leave a visible gap where a reading is null rather than
              // drawing a straight line through missing data.
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/components/DataTable.tsx`**

```tsx
import { useEffect, useState } from 'react'

import { clampPage, pageCount, paginate, type DailyRow } from '../lib/transform'

const PAGE_SIZES = [10, 20, 50]

const COLUMNS: { key: keyof DailyRow; label: string }[] = [
  { key: 'date', label: 'Date' },
  { key: 'tempMax', label: 'Max °C' },
  { key: 'tempMin', label: 'Min °C' },
  { key: 'feelsMax', label: 'Feels max °C' },
  { key: 'feelsMin', label: 'Feels min °C' },
]

export function DataTable({ rows }: { rows: DailyRow[] }) {
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)

  // A file with fewer rows, or a larger page size, can strand us past the end.
  useEffect(() => {
    setPage((current) => clampPage(current, rows.length, pageSize))
  }, [rows.length, pageSize])

  const totalPages = pageCount(rows.length, pageSize)
  const visible = paginate(rows, page, pageSize)

  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-500">Nothing to tabulate.</p>
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="px-3 py-2 text-left font-medium whitespace-nowrap text-slate-600"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visible.map((row) => (
              <tr key={row.date} className="hover:bg-slate-50">
                {COLUMNS.map((column) => {
                  const value = row[column.key]
                  return (
                    <td
                      key={column.key}
                      className="px-3 py-2 whitespace-nowrap text-slate-700"
                    >
                      {value === null ? <span className="text-slate-400">—</span> : value}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <label className="flex items-center gap-2 text-slate-600">
          Rows per page
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
            className="rounded-md border border-slate-300 px-2 py-1"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={page === 1}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-600">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            disabled={page === totalPages}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TempChart.tsx frontend/src/components/DataTable.tsx
git commit -m "feat(ui): add temperature chart and paginated data table"
```

---

## Task 15: App composition and responsive layout

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: every component and API function built so far
- Produces: the complete dashboard

- [ ] **Step 1: Replace `frontend/src/App.tsx`**

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getWeatherFileContent, listWeatherFiles } from './api/client'
import { DataTable } from './components/DataTable'
import { FileList } from './components/FileList'
import { InputPanel } from './components/InputPanel'
import { StatusBanner } from './components/StatusBanner'
import { TempChart } from './components/TempChart'
import { useAsync } from './hooks/useAsync'
import { toDailyRows } from './lib/transform'
import type { StoredFileMeta, WeatherPayload } from './types'

export default function App() {
  const [files, setFiles] = useState<StoredFileMeta[]>([])
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [payload, setPayload] = useState<WeatherPayload | null>(null)

  // Loaded files are cached by name, so re-clicking one costs no request.
  const cache = useRef(new Map<string, WeatherPayload>())

  const listing = useAsync(listWeatherFiles)
  const content = useAsync(getWeatherFileContent)

  const refreshFiles = useCallback(async () => {
    const result = await listing.run()
    if (result) setFiles(result)
  }, [listing])

  useEffect(() => {
    void refreshFiles()
    // Run once on mount. refreshFiles is stable enough for this purpose and
    // re-running on its identity would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectFile = useCallback(
    async (name: string) => {
      setSelectedName(name)

      const cached = cache.current.get(name)
      if (cached) {
        setPayload(cached)
        return
      }

      const result = await content.run(name)
      if (result) {
        cache.current.set(name, result)
        setPayload(result)
      } else {
        setPayload(null)
      }
    },
    [content],
  )

  // Chart and table are derived from the loaded payload — never a second copy.
  const rows = useMemo(() => (payload ? toDailyRows(payload) : []), [payload])

  const selectedMeta = files.find((file) => file.name === selectedName)

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
          <h1 className="text-xl font-bold text-slate-800 sm:text-2xl">Weather Explorer</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Historical daily weather from Open-Meteo, stored in Google Cloud Storage.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[22rem_1fr]">
          <div className="space-y-6">
            <InputPanel
              onStored={(name) => {
                void refreshFiles().then(() => selectFile(name))
              }}
            />
            <FileList
              files={files}
              loading={listing.loading}
              error={listing.error}
              selectedName={selectedName}
              onSelect={(name) => void selectFile(name)}
              onRefresh={() => void refreshFiles()}
            />
          </div>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-semibold text-slate-800">Visualization</h2>

            {content.error && <StatusBanner kind="error" message={content.error} />}

            {content.loading && (
              <p className="py-12 text-center text-sm text-slate-500">Loading file…</p>
            )}

            {!content.loading && !payload && !content.error && (
              <StatusBanner
                kind="info"
                message="Select a stored file to see its chart and table."
              />
            )}

            {!content.loading && payload && (
              <div className="space-y-5">
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <Metadata label="Latitude" value={payload.latitude?.toFixed(4) ?? '—'} />
                  <Metadata label="Longitude" value={payload.longitude?.toFixed(4) ?? '—'} />
                  <Metadata label="Timezone" value={payload.timezone ?? '—'} />
                  <Metadata label="Days" value={String(rows.length)} />
                </dl>

                {selectedMeta && (
                  <p className="truncate font-mono text-xs text-slate-500">
                    {selectedMeta.name}
                  </p>
                )}

                <TempChart rows={rows} />
                <DataTable rows={rows} />
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  )
}
```

- [ ] **Step 2: Verify the build and run end-to-end locally**

```bash
cd frontend && npm run build
```
Expected: succeeds.

Start the backend in one terminal and the frontend in another:

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```
```bash
cd frontend && npm run dev
```

At this point there is still no bucket, so **Fetch & store** will report a storage error — that is expected and confirms error handling works. Verify:

- The page renders with the input panel and file list side by side on a wide window, stacked on a narrow one.
- Entering latitude `999` and submitting shows a validation message with no network request (check the Network tab).
- **Fetch & store** with valid input shows a red banner carrying the backend's message.
- The file list shows the empty state.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): compose responsive dashboard with per-panel states"
```

---

## Task 16: Deploy the backend to Cloud Run

**Files:**
- Create: `DEPLOY.md`

**Interfaces:**
- Consumes: `backend/Dockerfile`
- Produces: a live backend URL; `DEPLOY.md` recording the exact commands

> **This task needs interactive authentication.** Ask the user to run the `gcloud auth` steps themselves by typing `! <command>`, then continue.

- [ ] **Step 1: Install and authenticate the gcloud CLI**

Ask the user to install the Google Cloud CLI if `gcloud` is missing (https://cloud.google.com/sdk/docs/install), then run:

```bash
gcloud auth login
gcloud auth application-default login
```

- [ ] **Step 2: Create the project and enable APIs**

Choose a globally unique project id and bucket name. Substitute them throughout.

```bash
export PROJECT_ID=inrisk-weather-<yourname>
export REGION=asia-south1
export BUCKET=inrisk-weather-data-<yourname>

gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID
```

Billing must be linked to the project before Cloud Run and Cloud Build will work — the user does this in the console (https://console.cloud.google.com/billing). Cloud Run's always-free tier still applies; linking billing does not by itself incur charges.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com storage.googleapis.com artifactregistry.googleapis.com
```

- [ ] **Step 3: Create the bucket**

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
```

Verify:

```bash
gcloud storage buckets describe gs://$BUCKET --format="value(name,location)"
```
Expected: the bucket name and region.

- [ ] **Step 4: Create a least-privilege service account**

```bash
gcloud iam service-accounts create weather-api --display-name="Weather Explorer API"

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:weather-api@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

Granting on the bucket rather than the project keeps the service account's reach to exactly one bucket.

- [ ] **Step 5: Deploy**

`ALLOWED_ORIGINS` is a placeholder for now — the real Vercel URL does not exist yet, and Task 17 tightens it.

```bash
cd backend

gcloud run deploy weather-api \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --service-account weather-api@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars "GCS_BUCKET=$BUCKET,ALLOWED_ORIGINS=http://localhost:5173"
```

Capture the service URL it prints:

```bash
export API_URL=$(gcloud run services describe weather-api --region $REGION --format="value(status.url)")
echo $API_URL
```

- [ ] **Step 6: Verify all three endpoints live**

```bash
curl -s $API_URL/health
```
Expected: `{"status":"ok"}`

```bash
curl -s -X POST $API_URL/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":19.076,"longitude":72.8777,"start_date":"2024-06-01","end_date":"2024-06-10"}'
```
Expected: `{"status":"ok","file":"weather_19.0760_72.8777_2024-06-01_2024-06-10_...json"}`

```bash
curl -s $API_URL/list-weather-files
```
Expected: a `files` array containing the object just written, with `size` and `created_at`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" $API_URL/weather-file-content/nope.json
```
Expected: `404`

```bash
curl -s -X POST $API_URL/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":999,"longitude":0,"start_date":"2024-06-01","end_date":"2024-06-10"}'
```
Expected: HTTP 400 with `{"status":"error","message":"latitude: ..."}`

Confirm the object really landed in the bucket:

```bash
gcloud storage ls gs://$BUCKET
```

- [ ] **Step 7: Write `DEPLOY.md`**

Record every command above with the real project id, region, bucket, and service URL substituted in, under headings `Prerequisites`, `Backend (Cloud Run)`, `Frontend (Vercel)` (to be filled in next task), and `Redeploying`. Include the one-command redeploy:

```bash
cd backend && gcloud run deploy weather-api --source . --region <REGION>
```

- [ ] **Step 8: Commit**

```bash
git add DEPLOY.md
git commit -m "docs: add deployment runbook for Cloud Run"
```

---

## Task 17: Deploy the frontend, lock CORS, and write the README

**Files:**
- Create: `README.md`
- Modify: `DEPLOY.md`

**Interfaces:**
- Consumes: the live backend URL from Task 16
- Produces: a live dashboard URL, CORS restricted to it, and submission-ready documentation

- [ ] **Step 1: Push to GitHub**

```bash
gh repo create inrisk-weather-explorer --public --source=. --remote=origin --push
```

If `gh` is unavailable, ask the user to create the public repo in the browser and then:

```bash
git remote add origin https://github.com/<user>/inrisk-weather-explorer.git
git push -u origin main
```

- [ ] **Step 2: Deploy to Vercel**

```bash
npm install -g vercel
cd frontend
vercel login
```

Then deploy, answering the prompts (framework: Vite; root directory: current; build command and output directory: defaults):

```bash
vercel --prod
```

Set the API base URL and redeploy so it is baked into the bundle:

```bash
vercel env add VITE_API_BASE production
# paste the Cloud Run URL from Task 16, with no trailing slash
vercel --prod
```

Capture the production URL Vercel prints — call it `<VERCEL_URL>`.

- [ ] **Step 3: Lock CORS to the real frontend origin**

This is the deliberate second pass: neither service could know the other's URL until both existed.

```bash
gcloud run services update weather-api \
  --region $REGION \
  --update-env-vars "ALLOWED_ORIGINS=<VERCEL_URL>"
```

- [ ] **Step 4: Verify the full deployed flow**

Confirm CORS now permits the real origin and rejects others:

```bash
curl -s -I -X OPTIONS $API_URL/store-weather-data \
  -H "Origin: <VERCEL_URL>" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin
```
Expected: the header echoes `<VERCEL_URL>`.

```bash
curl -s -I -X OPTIONS $API_URL/store-weather-data \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin
```
Expected: no `access-control-allow-origin` header.

Then open `<VERCEL_URL>` in a browser and walk the whole flow:

1. Submit a valid location and date range → a success banner shows the stored filename.
2. The file list refreshes and the new file is selected automatically.
3. The chart draws four series; the table lists the same days.
4. Change page size to 20 and 50 — pagination stays in range.
5. Submit latitude `999` → a validation message appears with no network request.
6. Submit a 40-day range → a 400 with the "31 days" message.
7. Resize to a phone width → panels stack, the table scrolls horizontally, nothing overflows the page.
8. Click an already-loaded file again → it renders instantly with no new network request (verify in the Network tab).

- [ ] **Step 5: Write `README.md`**

It must contain:

- **Live URLs** — the dashboard and the API, plus `Last verified live: <date>`.
- **What it does** — the three endpoints and the dashboard flow, in a short paragraph.
- **Architecture** — the diagram from the file structure section, and why storage sits behind a protocol (testability without credentials).
- **Setup** — clone, backend venv + `pip install -r requirements.txt` + `uvicorn`, frontend `npm install` + `npm run dev`, and the two environment variables with `.env.example` pointers.
- **Running the tests** — `pytest` for the backend, `npm test` for the frontend, with the note that neither needs cloud credentials or network access.
- **Libraries used and why** — FastAPI (declarative validation, free OpenAPI docs), pydantic, google-cloud-storage, httpx + respx, Recharts, Tailwind 4.
- **Design decisions and assumptions** — carry these across from the spec verbatim, since they are what the follow-up discussion will probe:
  1. "Range ≤ 31 days" read as an inclusive day count; Jun 1 → Jul 1 passes, Jun 1 → Jul 2 fails.
  2. "Full API JSON" means the response body is stored unmodified.
  3. Date bounds beyond the brief (no future dates, nothing before 1940-01-01) are validated server-side because Open-Meteo rejects them anyway — a clear 400 beats a 502 wrapping an upstream error.
  4. A malformed filename and a missing filename both return 404; refusing to distinguish them is the traversal defense and leaks nothing.
  5. Listing is unpaginated, but uses a `fields` mask so one SDK call returns only name, size, and creation time.
  6. CORS uses an explicit origin allowlist, not `*`.
  7. The browser never calls Open-Meteo; loaded files are cached in memory by name.
- **Redeploying** — point at `DEPLOY.md`.

- [ ] **Step 6: Finish `DEPLOY.md`**

Fill in the `Frontend (Vercel)` section with the commands from Step 2 and the CORS update from Step 3.

- [ ] **Step 7: Final verification**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v
cd ../frontend && npm test && npm run build
```
Expected: every test passes and the build succeeds.

Confirm no secrets were committed:

```bash
git ls-files | grep -Ei "\.env$|credential|service-account|\.json$" || echo "clean"
```
Expected: no `.env` or service-account key files.

- [ ] **Step 8: Commit and push**

```bash
git add README.md DEPLOY.md
git commit -m "docs: add README with live URLs, setup, and design decisions"
git push
```

---

## Definition of Done

- [ ] All three endpoints live on Cloud Run and verified with `curl`
- [ ] Dashboard live on Vercel and verified end-to-end in a browser
- [ ] `ALLOWED_ORIGINS` restricted to the real Vercel origin, verified positively and negatively
- [ ] Backend suite passes with no credentials and no network
- [ ] Frontend transform tests pass; production build succeeds
- [ ] Public GitHub repo with incremental, conventional commits
- [ ] README carries live URLs, last-verified date, setup, and the seven design decisions
- [ ] No credentials of any kind in git history
