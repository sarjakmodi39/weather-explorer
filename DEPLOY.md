# Deploying Weather Explorer

A runbook for taking this app from a local checkout to a live backend
(Cloud Run) and frontend (Vercel), in the region **asia-south1** (Mumbai).

Backend and frontend cannot know each other's URLs until both exist, so this
is deliberately two passes: deploy the backend with CORS wide open, deploy
the frontend against it, then come back and lock CORS down to the real
frontend origin. That second pass is not an oversight — it's the only order
that's possible, since Vercel doesn't hand out a URL until after the first
deploy, and Cloud Run needs a value for `ALLOWED_ORIGINS` before that URL
exists.

Placeholders are marked `<PLACEHOLDER>`. Some are values you choose up front
(project ID, bucket name); others are outputs you only get after running a
command (service URL, Vercel URL) — each is labeled below.

## Prerequisites

1. Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install).
2. Authenticate:

   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

   The first authenticates the CLI itself; the second sets up Application
   Default Credentials, which is how `GCSStorage` authenticates locally
   without a key file (see README, "Credentials").

3. Link a billing account to your GCP project. Cloud Run and Cloud Build both
   require an active billing account even though this deployment stays
   within their always-free tiers (Cloud Run: 2M requests/month; Cloud Build:
   120 build-minutes/day; GCS: 5GB). You will not be charged unless you
   exceed those limits.

## Backend (Cloud Run)

### 1. Create the project and enable APIs

```bash
gcloud projects create <GCP_PROJECT_ID>          # you choose this
gcloud config set project <GCP_PROJECT_ID>

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com
```

### 2. Create the bucket

```bash
gcloud storage buckets create gs://<GCS_BUCKET_NAME> \
  --location=asia-south1 \
  --uniform-bucket-level-access
```

`<GCS_BUCKET_NAME>` — you choose this; must be globally unique.
Uniform bucket-level access means permissions are granted only via IAM
(the service account below), never per-object ACLs.

### 3. Create a service account scoped to one bucket

```bash
gcloud iam service-accounts create weather-explorer-run \
  --display-name="Weather Explorer Cloud Run service account"

gcloud storage buckets add-iam-policy-binding gs://<GCS_BUCKET_NAME> \
  --member="serviceAccount:weather-explorer-run@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

Grant `roles/storage.objectAdmin` **on the bucket**, not on the project. A
project-level grant would let this service account read and write every
bucket in the project, present or future. Scoping it to one bucket means a
compromised Cloud Run service can, at worst, read or overwrite weather
files — nothing else in the project is reachable through it.

### 4. Deploy

From the `backend/` directory:

```bash
cd backend
gcloud run deploy weather-explorer-api \
  --source . \
  --region=asia-south1 \
  --allow-unauthenticated \
  --service-account="weather-explorer-run@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --set-env-vars="GCS_BUCKET=<GCS_BUCKET_NAME>,ALLOWED_ORIGINS=*"
```

`--source .` builds the `Dockerfile` in this directory via Cloud Build and
deploys the image — no separate `docker build`/`push` step.
`--allow-unauthenticated` is required for a public dashboard to call this
API; see README point 9 on what a private deployment would add instead.
`ALLOWED_ORIGINS=*` here is intentionally temporary — Starlette's
`CORSMiddleware` accepts it as a literal placeholder value during this first
pass; it gets replaced with the real frontend origin in the CORS lockdown
step below, and should never be left this way in a deployment anyone else
depends on.

The command prints a service URL on success:

```
Service URL: <CLOUD_RUN_URL>
```

`<CLOUD_RUN_URL>` is an output of this step — copy it for the checks below
and for the frontend's `VITE_API_BASE`.

### 5. Verify

```bash
# Health check
curl -s <CLOUD_RUN_URL>/health
# {"status":"ok"}

# List (empty bucket)
curl -s <CLOUD_RUN_URL>/list-weather-files
# {"files":[]}

# Store — Mumbai, a 7-day window
curl -s -X POST <CLOUD_RUN_URL>/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":19.0760,"longitude":72.8777,"start_date":"2026-07-01","end_date":"2026-07-07"}'
# {"status":"ok","file":"weather_19.0760_72.8777_2026-07-01_2026-07-07_<timestamp>.json"}

# Missing file -> 404
curl -s -o /dev/null -w "%{http_code}\n" <CLOUD_RUN_URL>/weather-file-content/does-not-exist.json
# 404

# Bad request -> 400 (latitude out of range)
curl -s -X POST <CLOUD_RUN_URL>/store-weather-data \
  -H "Content-Type: application/json" \
  -d '{"latitude":999,"longitude":72.8777,"start_date":"2026-07-01","end_date":"2026-07-07"}'
# {"status":"error","message":"latitude: Input should be less than or equal to 90"}
```

## Frontend (Vercel)

### 1. Set `VITE_API_BASE` before building

Vite inlines environment variables into the JavaScript bundle at build time
— they are not read at runtime by the deployed static files. `VITE_API_BASE`
must be set to `<CLOUD_RUN_URL>` **before** Vercel runs its production
build, or the shipped bundle will target the wrong (or no) backend and every
API call will fail until the next rebuild.

In the Vercel dashboard: Project → Settings → Environment Variables →
add `VITE_API_BASE` = `<CLOUD_RUN_URL>` for the Production environment.
Or via CLI from `frontend/`:

```bash
cd frontend
vercel env add VITE_API_BASE production
# paste <CLOUD_RUN_URL> when prompted
```

### 2. Deploy

```bash
vercel --prod
```

Vercel prints the production URL:

```
<VERCEL_URL>
```

`<VERCEL_URL>` is an output of this step.

## CORS lockdown (second pass)

Now that `<VERCEL_URL>` exists, tighten `ALLOWED_ORIGINS` on Cloud Run from
the temporary `*` to the real origin:

```bash
gcloud run services update weather-explorer-api \
  --region=asia-south1 \
  --update-env-vars="ALLOWED_ORIGINS=<VERCEL_URL>"
```

Verify both directions:

```bash
# Positive: the real frontend origin gets a CORS header
curl -s -o /dev/null -D - <CLOUD_RUN_URL>/health -H "Origin: <VERCEL_URL>" \
  | grep -i access-control-allow-origin
# access-control-allow-origin: <VERCEL_URL>

# Negative: any other origin gets no CORS header at all
curl -s -o /dev/null -D - <CLOUD_RUN_URL>/health -H "Origin: https://evil.example.com" \
  | grep -i access-control-allow-origin
# (no output — header absent)
```

If the negative check prints a header, `ALLOWED_ORIGINS` still contains `*`
or an overly broad value — re-check the env var above.

## Redeploying

**Backend** — from `backend/`, one command re-runs the same build-and-deploy:

```bash
gcloud run deploy weather-explorer-api --source . --region=asia-south1
```

Cloud Run keeps the existing env vars and service account unless you pass
`--set-env-vars`/`--service-account` again.

**Frontend** — from `frontend/`, after any code change or if
`VITE_API_BASE` changes:

```bash
vercel --prod
```

Because `VITE_API_BASE` is inlined at build time, changing that value alone
(without redeploying) has no effect — a redeploy is the only way to pick up
a new backend URL.
