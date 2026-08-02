# Weather Explorer

A small full-stack app: fetch historical daily weather from Open-Meteo, store the
raw response in Google Cloud Storage, and browse it in a dashboard. Built as a
case study for InRisk Labs.

## Live URLs

- **Dashboard:** _Pending deployment — see DEPLOY.md_
- **API:** _Pending deployment — see DEPLOY.md_
- **Last verified live:** _Pending deployment — see DEPLOY.md_

## What it does

The backend exposes three endpoints:

- `POST /store-weather-data` — fetch a lat/lon/date-range window from Open-Meteo's
  archive API and store the response as JSON.
- `GET /list-weather-files` — list stored files: name, size, creation time.
- `GET /weather-file-content/{file}` — return one stored file's JSON.

The dashboard lets you pick coordinates and a date range, fetch and store a
file, browse previously stored files, and load one to see a temperature chart
and a paginated data table.

## Architecture

```
backend/
  app/
    main.py              app factory, CORS, exception handlers
    config.py            env-driven settings (GCS_BUCKET, ALLOWED_ORIGINS)
    schemas.py            request/response models, validation
    naming.py             object name construction + traversal-safe validation
    errors.py              AppError -> uniform JSON error body
    deps.py                 dependency providers (storage)
    routes/weather.py      the three endpoints — thin, no business logic
    services/
      open_meteo.py        httpx client for the archive API
      storage.py            StorageClient protocol + GCSStorage + InMemoryStorage
  tests/
  Dockerfile
frontend/
  src/
    api/client.ts          the only module that knows the backend exists
    components/            InputPanel, FileList, TempChart, DataTable, StatusBanner
    hooks/useAsync.ts       per-panel loading/error state
    lib/transform.ts        pure functions: JSON -> chart rows, pagination, validation
README.md
DEPLOY.md
```

### Why storage sits behind a Protocol

`backend/app/services/storage.py` defines a `StorageClient` Protocol with three
methods: `save_json`, `list_files`, `get_json`. There are two implementations —
`GCSStorage` for production, `InMemoryStorage` for tests — and every route
depends on the Protocol via FastAPI's `Depends(get_storage)`, never on
`google.cloud.storage` directly.

This is the single most defensible decision in the project: it is what lets
all 90 backend tests run with no cloud credentials and no network access. A
test overrides `get_storage` with `lambda: InMemoryStorage()` and gets the same
observable behavior — same `StoredFile` shape, same sort order, same
"missing file returns `None`" contract — without ever touching GCS. The
alternative (mocking `google.cloud.storage.Client` per test) would couple
every test to the SDK's internals instead of to the behavior that matters.

## Setup

Clone the repo, then set up each side independently.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
cp .env.example .env              # edit GCS_BUCKET, ALLOWED_ORIGINS as needed
uvicorn app.main:app --reload
```

`requirements-dev.txt` pulls in `requirements.txt` plus test tooling
(`pytest`, `respx`, `pytest-asyncio`), so one install covers both running the
app and running its tests.

Environment variables (see `backend/.env.example`):

| Variable | Purpose | Local default |
|---|---|---|
| `GCS_BUCKET` | Name of the bucket holding stored weather files | `""` (empty — fine until you store something) |
| `ALLOWED_ORIGINS` | Comma-separated CORS allowlist | `http://localhost:5173` |

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local        # set VITE_API_BASE
npm run dev
```

`frontend/.env.example` documents `VITE_API_BASE` — the backend's base URL,
no trailing slash. Vite inlines this value into the JavaScript bundle **at
build time**, not read at runtime. Changing it after a build has already run
requires rebuilding (`npm run build`); editing the deployed `dist/` output or
setting the variable in the browser does nothing.

## Running the tests

```bash
cd backend  && pytest        # 90 tests
cd frontend && npm test      # 31 tests
```

Neither suite needs cloud credentials or network access. The backend swaps
`InMemoryStorage` in via dependency override and stubs Open-Meteo with
`respx`; the frontend tests are pure functions (`lib/transform.ts`) with no
fetch calls to mock.

## Libraries used and why

**Backend**

| Library | Why |
|---|---|
| FastAPI | Declarative request validation via pydantic models, so the graded rules live in `schemas.py` instead of hand-rolled `if` chains; free `/docs` for reviewers. |
| pydantic | Backs FastAPI's validation and gives typed response models — the shape of every response is enforced, not just documented. |
| google-cloud-storage | The brief names GCS first, and its always-free 5GB tier fits a case study. |
| httpx | Async HTTP client that fits FastAPI's async route handlers without blocking the event loop. |
| respx | Mocks `httpx` at the transport layer, so tests never make a real request to Open-Meteo. |
| pytest | Standard, minimal-ceremony test runner; fixtures (`conftest.py`) keep the storage override in one place. |

**Frontend**

| Library | Why |
|---|---|
| React | Component model matches the app's shape: a handful of independent panels sharing one piece of derived state. |
| Vite | Fast dev server and a build step that inlines env vars at build time (see `VITE_API_BASE` above). |
| Tailwind 4 | Utility classes kept every component's styling local — no separate CSS files to keep in sync with markup. |
| Recharts | Declarative line chart that maps directly onto the four daily variables; hand-rolled SVG would be more code to defend for no visual gain. |
| vitest | Vite-native test runner — no separate config to bridge build tooling and test tooling. |

## Design decisions and assumptions

### 1. "Range ≤ 31 days" is an inclusive day count

`backend/app/schemas.py` computes `span = (end_date - start_date).days + 1`
and rejects anything over `MAX_RANGE_DAYS = 31`. Jun 1 → Jul 1 is 31 days and
passes; Jun 1 → Jul 2 is 32 and fails. The frontend's `validateInputs` in
`frontend/src/lib/transform.ts` mirrors this exact arithmetic so a client-side
mistake costs no round trip — the server remains the authority.

### 2. "Full API JSON" means unmodified content, not unmodified bytes

The brief says "full API JSON." `POST /store-weather-data` stores
Open-Meteo's parsed response with no reshaping and no field stripping. In
honesty: storage re-serializes a parsed Python dict (`json.dumps(payload)`),
so the JSON *value* is byte-for-byte equivalent in content, but whitespace,
key order, and number formatting from the original wire response are not
preserved. If a reviewer needs the literal upstream bytes, this is the one
place semantics diverge from the raw response — the parsed content survives
intact.

### 3. Extra date bounds are validated server-side, and "today" is UTC

The brief specifies range and ordering rules; it doesn't mention future dates
or how far back the archive goes. `schemas.py` additionally rejects
`end_date` in the future and `start_date` before `1940-01-01`, because
Open-Meteo's archive rejects both anyway. Validating locally turns an upstream
502 (Open-Meteo's own rejection, wrapped) into a direct 400 with a specific
reason — a strictly better experience for the caller. "Today" is evaluated as
`datetime.now(timezone.utc).date()`, not the server's local clock or the
client's — so a request that is valid in one timezone and invalid in another
gets a single, unambiguous answer.

### 4. Malformed and missing filenames both return 404

`GET /weather-file-content/{file}` checks the filename against
`OBJECT_NAME_PATTERN` (in `backend/app/naming.py`) with `re.fullmatch` before
any storage call. If it doesn't match — wrong shape, traversal attempt, junk
— the route returns `404 {"status": "error", "message": "not found"}`, the
identical response a genuinely absent file gets. This is the path-traversal
defense: the filename travels toward a GCS blob lookup, so nothing that isn't
already one of our own names is allowed anywhere near it. Returning a
different code (or message) for "malformed" vs. "absent" would leak
information about what's actually in the bucket — a fingerprinting seam an
attacker could use to enumerate contents. Refusing to distinguish leaks
nothing.

### 5. Why the content route is `{file:path}`, not the brief's `{file}`

From `backend/app/routes/weather.py`:

> `{file:path}` rather than the brief's plain `{file}`: a single-segment
> converter matches against the *decoded* path, so a traversal string like
> `"../../etc/passwd"` would fail to match this route and fall through to
> Starlette's generic 404 ("Not Found", capital N) instead of the "not found"
> below — failing our own hostile-input test. The `:path` converter matches
> it here so `is_valid_object_name()` gets a chance to reject it.

In plain terms: FastAPI's default single-segment path parameter can't even
capture a string containing `/` after URL-decoding — the router itself
returns a generic 404 before the handler runs, so the endpoint's own
validation and its own error shape never fire. Using `{file:path}` lets a
hostile string reach the handler, where `is_valid_object_name()` rejects it
and returns the app's uniform error body instead of Starlette's default one.
This is a deliberate, documented departure from the given interface, made to
keep the *contract* (a consistent 404 shape for every kind of bad input) —
not a careless deviation.

### 6. Listing is unpaginated, but cheap

`GET /list-weather-files` makes one `list_blobs` call with a `fields` mask
(`items(name,size,timeCreated),nextPageToken`) so GCS returns only the three
fields the response needs — no per-object metadata fetches, no client-side
filtering. This assumes bucket contents stay small enough that no pagination
is needed (see Known limitations).

### 7. CORS is an explicit allowlist, and 500s still carry CORS headers

`ALLOWED_ORIGINS` is a comma-separated allowlist, never `*`
(`backend/app/config.py`). More subtly: unhandled exceptions are caught by a
`@app.middleware("http")` handler registered *before* `CORSMiddleware` is
added in `main.py`. Starlette's `add_middleware` inserts at index 0, so
registering the catch-all first makes `CORSMiddleware` the outermost layer.
This matters because Starlette routes `@app.exception_handler(Exception)` to
`ServerErrorMiddleware`, which sits *outside* `CORSMiddleware` in the default
stack — so without this extra layer, a genuine 500 would reach the browser
with no `access-control-allow-origin` header. The browser's fetch would then
be blocked client-side, and a real server error would look indistinguishable
from a network failure. `backend/tests/test_cors.py` asserts this directly
with a route that raises `RuntimeError`.

### 8. The browser never calls Open-Meteo

Only `backend/app/services/open_meteo.py` talks to Open-Meteo. The frontend
only ever calls the three backend endpoints. Loaded files are cached in
memory by name (`App.tsx`, a `useRef(new Map())`), so re-selecting an
already-loaded file is instant and costs no request — chart and table
re-render from data already in memory.

### 9. `POST /store-weather-data` is public and unauthenticated

This is deliberate for a case study: adding auth would add surface with
nothing to defend it (no user accounts, no data worth protecting beyond rate
limiting). In a real deployment, the first thing to add would be an API key
or a Cloud Run IAM-authenticated invoker, plus basic rate limiting in front
of the store endpoint — it is the one that costs an outbound call and writes
storage.

### 10. Timestamps: UTC in storage, local in the UI

Object names embed a UTC timestamp (`naming.py`,
`YYYYMMDDTHHMMSSZ`) so names sort and compare unambiguously regardless of
where the server or the caller sit. `FileList.tsx` renders `created_at` with
`toLocaleString()`, so the same file shows a UTC name next to a
locally-formatted time in the viewer's own timezone — deliberately different
representations for different audiences (machine-sortable vs. human-readable).

## Known limitations

- **Second-granularity filenames.** The timestamp component is
  `%Y%m%dT%H%M%SZ` — seconds, not milliseconds. Two identical requests
  (same lat/lon/dates) completed within the same UTC second produce the same
  object name and the second overwrites the first.
- **Recharts bundle size.** The production build's main chunk is ~570KB,
  over Vite's 500KB warning threshold. It builds and runs fine; no code
  splitting has been added, since a single-page dashboard has nothing
  meaningful to split into a separate route.
- **No authentication.** See point 9 above.

## Redeploying

See `DEPLOY.md` for the full runbook — Cloud Run for the backend, Vercel for
the frontend, and the two-pass CORS lockdown once both URLs exist.
