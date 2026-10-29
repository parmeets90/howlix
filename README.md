# Howlix

**Find the moments worth watching.**

Howlix is an AI-powered video clipping product by Wolvesgang Digital. This repository contains the Milestone 2 ingestion foundation: a polished Next.js workspace, FastAPI APIs, Supabase Postgres metadata, direct browser-to-Cloudflare-R2 multipart uploads, and a local FFprobe validation worker.

> This remains a single-user local development environment. It has no authentication and must not be exposed as a public multi-user service.

## Repository layout

```text
howlix/
├── frontend/   # Next.js App Router, TypeScript, Tailwind CSS, shadcn-style UI
├── backend/    # FastAPI, Pydantic, SQLAlchemy, Alembic, pytest
├── storage/    # Future local media/cache data (ignored by Git)
└── docs/       # Architecture, roadmap, and milestone notes
```

## Prerequisites (Windows 64-bit)

- Node.js 20.9 or newer and npm
- Python 3.11
- Git
- A Supabase project and its Postgres connection string
- FFmpeg/FFprobe
- A private Cloudflare R2 bucket named `howlix-media` and bucket-scoped S3 credentials

The initial environment inspection found Node.js 24.11.1, npm 11.6.2, Python 3.12.10, and Git 2.54.0. Python 3.11 and FFmpeg/FFprobe were not found. Install them from PowerShell if needed; these commands are intentionally not run automatically:

```powershell
winget install --id Python.Python.3.11 --exact
winget install --id Gyan.FFmpeg --exact
```

Open a new PowerShell window after installation, then verify:

```powershell
py -3.11 --version
ffmpeg -version
ffprobe -version
```

## First-time setup

Run all commands from the repository root unless a command changes directory.

### Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cd ..
Copy-Item .env.example .env
```

Open the Supabase dashboard, select the project, click **Connect**, choose the **Session pooler** connection for reliable IPv4 development, and place that URI in the root `.env` as `HOWLIX_DATABASE_URL`. Replace the password placeholder and retain `sslmode=require`. Password characters such as `@`, `#`, `?`, or spaces must be URL-encoded. Then add the private R2 account ID and bucket-scoped S3 credentials described in [Cloudflare R2 setup](docs/cloudflare-r2-setup.md).

Then apply the schema:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
cd ..
```

If PowerShell blocks virtual-environment activation, use this for the current process and retry activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Frontend

```powershell
cd frontend
npm install
cd ..
```

The Supabase URI is a backend secret. Never put it in `NEXT_PUBLIC_*` variables or commit `.env`. Local ports default to 3000 and 8000. For a different frontend API URL, copy `NEXT_PUBLIC_API_URL` into `frontend/.env.local`.

## Run Howlix

Open three PowerShell windows at the repository root.

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

Validation worker:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Open [http://localhost:3000](http://localhost:3000). API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs), and health status at [http://localhost:8000/health](http://localhost:8000/health).

## Tests and checks

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

Frontend:

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

The normal test suite mocks R2 and never writes to Cloudflare. The optional real R2 test requires valid credentials and explicit opt-in:

```powershell
$env:RUN_R2_INTEGRATION_TESTS="true"
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -m integration tests\test_r2_integration.py
```

## Milestone 2 scope

Implemented:

- Responsive Howlix landing page and local dashboard
- Real project creation, listing, and retrieval through FastAPI
- Supabase Postgres persistence managed by SQLAlchemy and Alembic
- Private, server-controlled R2 object keys
- Direct multipart uploads with 16 MiB parts and two concurrent browser requests
- Real XHR byte progress, pause, resume, cancel, retry, and expired-URL refresh
- Refresh recovery after reselecting the same local file
- Persisted upload sessions, media assets, and lease-backed validation jobs
- FFprobe container, duration, codec, resolution, and frame-rate validation
- Private, short-lived video previews and project media status pages
- Mocked R2 tests plus an explicit opt-in integration test

Not implemented:

- Transcription or AI analysis
- Clip generation, cropping, caption rendering, or exports
- Authentication, billing, or public deployment

Media validation runs as a background worker, but distributed job infrastructure is intentionally not introduced yet.

See [the architecture](docs/architecture.md), [Cloudflare R2 setup](docs/cloudflare-r2-setup.md), [Supabase setup](docs/supabase.md), [roadmap](docs/roadmap.md), and [Milestone 2 notes](docs/milestone-2.md) for more detail.

