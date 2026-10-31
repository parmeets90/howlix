# Howlix

**Find the moments worth watching.**

Howlix is an AI-powered video clipping product by Wolvesgang Digital. This repository contains the ingestion, transcription, moment-discovery, and Milestone 5 rendering pipeline: a polished Next.js workspace, FastAPI APIs, Supabase Postgres metadata, private Cloudflare R2 media, word-timestamp transcription, reviewed AI recommendations, and FFmpeg-rendered downloadable MP4 clips.

> This remains a single-user environment with no application authentication. Production-domain configuration is prepared for `howlix.wolvesgang.digital`, but the dashboard and API must stay behind a private access gate until authentication and authorization are implemented.

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
- Python 3.11 or newer
- Git
- A Supabase project and its Postgres connection string
- FFmpeg/FFprobe
- A private Cloudflare R2 bucket named `howlix-media` and bucket-scoped S3 credentials

The verified local environment uses Node.js 24.11.1, npm 11.6.2, Python 3.12.10, Git 2.54.0, and FFmpeg/FFprobe 9.0. Install missing tools from PowerShell if needed; these commands are intentionally not run automatically:

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id Gyan.FFmpeg --exact
```

Open a new PowerShell window after installation, then verify:

```powershell
py -3.12 --version
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -encoders | Select-String "h264_nvenc|libx264"
ffmpeg -hide_banner -filters | Select-String "ass"
```

## First-time setup

Run all commands from the repository root unless a command changes directory.

### Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cd ..
Copy-Item .env.example .env
```

Open the Supabase dashboard, select the project, click **Connect**, choose the **Session pooler** connection for reliable IPv4 development, and place that URI in the root `.env` as `HOWLIX_DATABASE_URL`. Replace the password placeholder and retain `sslmode=require`. Password characters such as `@`, `#`, `?`, or spaces must be URL-encoded. Keep `HOWLIX_DATABASE_SCHEMA=howlix`; this isolates Howlix from other applications sharing the Supabase project. Then add credentials scoped to the separate private `howlix-media` R2 bucket as described in [Cloudflare R2 setup](docs/cloudflare-r2-setup.md).

For cloud transcription and moment analysis, create a Groq API key and set `GROQ_API_KEY` in the root `.env`. It is read only by FastAPI and the worker. `TRANSCRIPTION_PROVIDER=groq`, `GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo`, and `GROQ_MOMENT_MODEL=openai/gpt-oss-20b` are the defaults. Never place the key in a `NEXT_PUBLIC_*` variable. Moment analysis sends timestamped transcript excerpts and metadata, never video bytes.

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

Validation, transcription, moment-discovery, and clip-render worker:

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

The optional live Groq test requires explicit opt-in and a small speech-audio fixture:

```powershell
$env:RUN_GROQ_INTEGRATION_TESTS="true"
$env:GROQ_INTEGRATION_AUDIO_PATH="C:\path\to\speech.flac"
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -m integration tests\test_groq_integration.py
```

The separate paid live moment-analysis check is also opt-in:

```powershell
$env:RUN_MOMENT_GROQ_INTEGRATION_TESTS="true"
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -m integration tests\test_moment_groq_integration.py
```

The real render round trip is opt-in because it downloads an original, encodes a clip, writes to R2, and downloads it again. Use an existing approved moment:

```powershell
$env:RUN_RENDER_INTEGRATION_TESTS="true"
$env:RENDER_INTEGRATION_MOMENT_ID="approved-moment-uuid"
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -m integration tests\test_render_integration.py -s
```

Run the offline, version-controlled recommendation evaluation with:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python evaluation\run_moment_evaluation.py
```

## Implemented scope

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
- Provider-neutral Groq and optional faster-whisper transcription
- FFmpeg speech-audio extraction and overlapping chunk processing
- Persisted transcripts, segments, words, language, real stages, and retries
- Searchable timestamped transcript viewer with video seeking
- Deterministic 20–90 second transcript candidate generation and word-level boundary refinement
- Provider-neutral Groq/fixture moment analysis with validated structured JSON
- Deterministic, normalized editorial scoring with visual quality marked unassessed
- Ranked, deduplicated, topic-diverse recommendations with durable retries and reproducibility metadata
- Moment review UI with preview-range playback, title/boundary edits, reset, approve, and reject actions
- Synthetic multilingual evaluation corpus and deterministic quality metrics
- Approved-moment exports in 9:16, 1:1, or 16:9 at 720p or 1080p
- Center, optional CPU face-aware, and normalized manual crop framing
- Minimal, bold, and karaoke ASS captions driven by real transcript-word timestamps
- Actual FFmpeg progress, cancellation, retries, NVENC probing, and libx264 fallback
- Private R2 export history with short-lived preview and download URLs

Not implemented:

- Authentication, billing, or public deployment

Media validation runs as a background worker, but distributed job infrastructure is intentionally not introduced yet.

See [the architecture](docs/architecture.md), [Cloudflare R2 setup](docs/cloudflare-r2-setup.md), [Supabase setup](docs/supabase.md), [roadmap](docs/roadmap.md), [Milestone 4 notes](docs/milestone-4.md), and [Milestone 5 notes](docs/milestone-5.md) for more detail.

Production URL and Git-connected deployment preparation are documented in [deployment.md](docs/deployment.md). The intended layout is `https://howlix.wolvesgang.digital` for Next.js and `https://api.howlix.wolvesgang.digital` for FastAPI.

