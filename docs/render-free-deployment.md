# Render Free API deployment

This deployment keeps the Howlix web API on one Render Free Web Service while
the existing Windows machine runs the durable worker. Supabase PostgreSQL is
the shared source of job and application state, and Cloudflare R2 remains the
private object store. Render does not host a database or worker in this setup.

```text
Vercel frontend -> Render FastAPI -> Supabase PostgreSQL / private R2
                                  ^
Windows worker -------------------+----> Groq / FFmpeg / private R2
```

When the Windows worker is offline, the authenticated API and uploads can
remain available, but queued transcription, discovery, YouTube import, and
render work will not progress. Do not describe this topology as continuously
operational processing.

## Repository configuration

The root `render.yaml` describes exactly one free web service. It deliberately
does not contain a Render database, background worker, migration command, or
pre-deploy command. `backend/requirements-api.txt` contains only API runtime
packages. Worker-only dependencies such as Groq, yt-dlp, faster-whisper,
OpenCV, and FFmpeg tooling are not needed to boot the web process.

Python is pinned to 3.12.10 in both the Blueprint and
`backend/.python-version`. The API starts one Uvicorn process because the free
instance is memory constrained.

## Create the Render service

No cloud change is performed by committing these files. Complete these steps
in the Render dashboard:

1. Choose **New > Blueprint**, connect the Howlix repository, and select the
   `main` branch. Review the plan before applying it: it must show one Web
   Service on the **Free** plan and no database.
2. Alternatively create **New > Web Service** and enter these exact values:
   - Runtime: `Python 3`
   - Branch: `main`
   - Root Directory: `backend`
   - Build Command: `python -m pip install --upgrade pip && python -m pip install -r requirements-api.txt`
   - Start Command: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - Health Check Path: `/health`
   - Instance Type: `Free`
   - Auto-deploy: disabled until the first verification is complete
3. Add the environment variables below. Never paste `.env` as a public file,
   and never add Supabase service-role credentials to Vercel or source control.
4. Deploy, then open `https://<service-name>.onrender.com/health`. A successful
   response is `{"status":"ok"}`.

Do not add `alembic upgrade`, `app.worker`, FFmpeg, or a second process to the
Render build/start commands.

## Render environment variables

Set these as secret or ordinary environment variables in Render as indicated.
Copy values from the local secret environment; do not copy placeholder text.

| Variable | Required value or purpose |
| --- | --- |
| `PYTHON_VERSION` | `3.12.10` |
| `HOWLIX_ENVIRONMENT` | `production` |
| `HOWLIX_DATABASE_URL` | Secret Supabase PostgreSQL connection URL with TLS; use the Supabase session pooler when direct IPv6 is unavailable |
| `HOWLIX_DATABASE_SCHEMA` | `howlix` |
| `HOWLIX_PUBLIC_APP_URL` | `https://howlix.wolvesgang.digital` |
| `HOWLIX_CORS_ORIGINS` | `https://howlix.wolvesgang.digital` (no trailing slash) |
| `HOWLIX_ALLOWED_HOSTS` | `<service-name>.onrender.com,api.howlix.wolvesgang.digital`; `*.onrender.com` is acceptable during initial Blueprint creation |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase publishable/anon key used by existing configuration |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `SUPABASE_JWT_ISSUER` | `https://<project-ref>.supabase.co/auth/v1` |
| `SUPABASE_JWKS_URL` | `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_VERIFICATION_MODE` | `jwks` |
| `AUTH_HTTP_TIMEOUT_SECONDS` | `10` |
| `R2_ACCOUNT_ID` | Secret Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | Secret R2 access key ID |
| `R2_SECRET_ACCESS_KEY` | Secret R2 access key secret |
| `R2_BUCKET_NAME` | Existing private Howlix bucket |
| `R2_REGION` | `auto` |
| `R2_ENDPOINT_URL` | Optional; otherwise derived from account ID |

Also review all quota, upload, presigned-URL expiry, and job-limit values in
`.env.production.example`. Keep their existing private-beta limits. Groq keys,
local model settings, FFmpeg paths, font paths, and yt-dlp settings belong on
the Windows worker, not on the Render API.

## Database migrations

The web service never migrates the database during startup. Run additive
migrations explicitly from a trusted development machine before deploying code
that requires them:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
alembic current
alembic upgrade head
alembic current
```

Back up or use Supabase recovery features before a future destructive schema
change. The current application expects the existing `howlix` schema and does
not need a Render PostgreSQL database.

## Vercel and domain steps

In the Vercel production environment set:

- `NEXT_PUBLIC_API_URL=https://<service-name>.onrender.com` initially, or
  `https://api.howlix.wolvesgang.digital` after the custom domain is verified.
- `NEXT_PUBLIC_SUPABASE_URL` to the existing project URL.
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` to the publishable/anon key.

Redeploy the frontend after changing `NEXT_PUBLIC_*` variables because Next.js
embeds them at build time. Do not expose the database URL, R2 secret, or a
Supabase service-role key in Vercel.

For the API custom domain, add `api.howlix.wolvesgang.digital` to the Render
service and then create the DNS record Render displays. Wait for certificate
issuance before changing Vercel's API URL. Keep the exact frontend origin in
CORS. In Supabase Auth, retain the production site URL and callback URLs for
`https://howlix.wolvesgang.digital` plus only the required local development
callbacks.

Direct browser multipart uploads require the existing R2 CORS policy to allow
`https://howlix.wolvesgang.digital`, the required upload methods/headers, and
exposure of `ETag`. R2 objects remain private; signing endpoints still require
a valid Supabase access token and ownership checks.

## Start the local Windows worker

The worker must use the same `HOWLIX_DATABASE_URL`,
`HOWLIX_DATABASE_SCHEMA`, R2 bucket/credentials, and Supabase project as the
Render API. Install the full worker requirements, not the API-only file:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
python -m app.worker
```

Install optional local transcription or face-detection requirements only when
those configured providers/modes are needed. Keep the terminal running and
prevent the Windows machine from sleeping during private-beta processing. One
worker is appropriate for the current low-memory configuration. Stopping it is
safe: lease-backed jobs remain in PostgreSQL and are recovered or retried by a
later worker, subject to their retry policy.

## Verification checklist

After the first deployment, use two distinct verified Supabase users:

1. Confirm `/health` returns 200 after any cold start.
2. Log in through the production frontend and list/create a project.
3. Start a multipart upload and confirm only signed R2 operations are returned.
4. Confirm user A cannot read, mutate, cancel, preview, or download user B's
   project, media, jobs, moments, or exports (404/403 according to the existing
   API convention).
5. Create a small authorized job through the deployed API while the Windows
   worker is running. Confirm the worker claims it from Supabase, writes status
   updates, uses private R2, and the authenticated UI observes completion.
6. For a real render verification, download and inspect the output for duration,
   A/V sync, framing, and captions. This is not proven merely by `/health`.

## Free-tier behavior and troubleshooting

- A free web service spins down after 15 minutes without inbound traffic. The
  next request can take about a minute while the service starts. The UI should
  tolerate this cold start; do not use artificial keep-alive traffic to imply
  paid-service availability.
- The filesystem is ephemeral. Never rely on local files for uploads, exports,
  job state, or configuration. Howlix stores durable state in Supabase and
  objects in private R2.
- Free instances have limited CPU and memory and cannot scale, attach a
  persistent disk, run one-off jobs, or provide SSH access. Keep one Uvicorn
  worker and leave all media processing on the Windows worker.
- Render provides 750 free instance hours per workspace per calendar month,
  plus separate bandwidth and build-pipeline limits. Exhaustion can suspend the
  service until the next allowance period or an upgrade.
- `502`/startup failure: verify `PYTHON_VERSION`, the API-only requirements,
  `$PORT`, and Render logs.
- Database connection failure: use the correct Supabase pooler URL, URL-encode
  password characters, require TLS, and confirm the `howlix` schema exists.
- Browser CORS failure: use the exact HTTPS Vercel origin without a trailing
  slash, and separately verify R2 CORS for direct uploads.
- `401`: verify issuer, audience, JWKS URL, token expiry, and that the frontend
  and backend use the same Supabase project. Never switch to unverified JWTs.
- Jobs stay queued: start the local worker and verify it points to the same
  Supabase database/schema and R2 bucket. The Render web process intentionally
  does not consume jobs.

Render explicitly positions free instances for experimentation rather than
production. This design is suitable for a constrained private beta, not a
production availability or security claim.
