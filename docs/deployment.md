# Deployment readiness for howlix.wolvesgang.digital

The repository is prepared for this production layout:

- Frontend: `https://howlix.wolvesgang.digital`
- FastAPI: `https://api.howlix.wolvesgang.digital`
- Database: the dedicated `howlix` schema inside Supabase PostgreSQL
- Media: the dedicated private `howlix-media` Cloudflare R2 bucket
- Worker: one persistent process with FFmpeg/FFprobe and the same backend secrets

DNS for both hostnames currently resolves, but DNS resolution alone does not mean either application has been deployed or verified. Connect the Git repository to the chosen hosting platform after the live Supabase and R2 checkpoint passes.

## Isolation requirements

Reusing the same cloud accounts does not mean sharing application data:

- Use the same Supabase project only with `HOWLIX_DATABASE_SCHEMA=howlix`. Alembic and runtime queries are restricted to this schema.
- Use a new R2 bucket named `howlix-media` and a new Object Read & Write token scoped only to that bucket.
- Never point Howlix at the CRM bucket, even under a different prefix. Separate buckets prevent lifecycle, CORS, retention, and credential changes from affecting the CRM.
- Never copy a Supabase service-role key into frontend configuration. Howlix requires the database Session pooler URI for SQLAlchemy.

## Security gate before deployment

Howlix does not yet implement user authentication or project authorization. Do not expose the dashboard or FastAPI unrestricted on the public Internet. Until application authentication is implemented, protect both hostnames with an identity-aware proxy such as Cloudflare Access, or an equivalent hosting-provider access policy restricted to the owner.

The R2 bucket remains private. Cloudflare Access protects the application hosts, not direct presigned R2 requests; those remain short-lived and object/operation scoped.

## Production environment

Use `.env.production.example` as the backend/worker variable inventory and `frontend/.env.production.example` for the public frontend build variable. Configure values in the hosting platform's secret manager; do not upload a real `.env` file or commit it to Git.

Important values:

```dotenv
HOWLIX_DATABASE_SCHEMA=howlix
HOWLIX_ENVIRONMENT=production
HOWLIX_PUBLIC_APP_URL=https://howlix.wolvesgang.digital
HOWLIX_CORS_ORIGINS=https://howlix.wolvesgang.digital
HOWLIX_ALLOWED_HOSTS=api.howlix.wolvesgang.digital
R2_BUCKET_NAME=howlix-media
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=<hosting-secret>
NEXT_PUBLIC_API_URL=https://api.howlix.wolvesgang.digital
```

Production mode disables FastAPI's interactive OpenAPI/Swagger endpoints. `/health` remains available for platform health checks.

## Required services

The deployment platform must support three processes or services:

1. Next.js frontend: install with `npm ci`, build with `npm run build`, run with `npm run start`.
2. FastAPI web process: install `backend/requirements.txt`, run migrations once, then run `uvicorn app.main:app --host 0.0.0.0 --port <platform-port>`.
3. Worker process: use the same backend image/environment and run `python -m app.worker` with exactly one replica.

The backend and worker runtime must include FFmpeg/FFprobe. Use persistent service processes; serverless functions are not suitable for the current worker loop and temporary video processing.

## Migration sequence

Before the first deployment:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
alembic current
alembic history --verbose
alembic upgrade head
alembic current
```

Review the pending revisions before `upgrade head`. The first live migration creates only the `howlix` schema and its application tables. Verify the CRM's `public` schema table count and application behavior are unchanged afterward.

## R2 browser CORS

Configure the exact policy in [cloudflare-r2-setup.md](cloudflare-r2-setup.md). It must include both local development and `https://howlix.wolvesgang.digital`, allow `PUT`, `GET`, and `HEAD`, and expose `ETag`. Do not enable `r2.dev`, a public custom domain, or wildcard origins.

## Git connection checklist

After the user creates the remote repository:

```powershell
git remote add origin <repository-url>
git branch -M main
git push -u origin main
```

Before connecting deployment automation, confirm `git status` is clean and verify no `.env` file is tracked:

```powershell
git status --short
git ls-files | Select-String -Pattern '(^|/)\.env($|\.)'
```

Only the non-secret `*.example` environment files should appear.

## Go-live verification

Run the Milestone 2.5 live test before public traffic:

1. Confirm the live Alembic revision and four Howlix tables inside the `howlix` schema.
2. Verify the separate R2 bucket, multipart operations, HeadObject, signed GET, and exact CORS headers.
3. Upload a disposable MP4 through the real frontend.
4. Run the worker and confirm verified metadata and private playback.
5. Delete the disposable project, rows, object, and incomplete multipart uploads.
6. Confirm the CRM dashboard and its R2-backed media remain unchanged.
