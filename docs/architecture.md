# Architecture

## Milestone 6 overview

Howlix uses a deliberately small local architecture that fits an 8 GB Windows development laptop.

```text
Browser (Next.js :3000 + Supabase SSR session)
  |                    |
  | control/status     | signed multipart PUT requests
  v                    v
FastAPI (:8000, verified bearer JWT)    private Cloudflare R2 bucket
  |                    ^
  v                    | download / delete / signed preview
Supabase Postgres  <- leased analysis/render worker -> Groq + FFmpeg/FFprobe
                              |
                              +-> private R2 originals and exports
```

The frontend and backend are independent applications. Supabase Auth manages credentials and cookie-backed frontend sessions. The browser attaches its access token to versioned `/api/v1` calls; FastAPI verifies it and scopes every database lookup by JWT subject. Video bytes still travel directly between the authorized browser and private R2 signed URLs. Alembic owns database schema changes.

## Frontend

- Next.js App Router and TypeScript
- Tailwind CSS with reusable shadcn-style primitives
- Lucide icons
- Client-side project reads and writes with explicit loading, empty, and error states
- A direct multipart uploader using 16 MiB slices, at most two concurrent XHR requests, and true byte progress
- Local recovery metadata that stores no credentials or signed URLs; the user must reselect the same browser file after refresh
- Project detail polling for persisted media and worker status
- A transcript viewer, ranked Moment Discovery review panel, and export settings/history UI with real progress
- Supabase SSR signup, login, recovery, logout, protected dashboard, and account usage UI

`frontend/lib/api.ts` is the frontend API boundary and attaches the current Supabase access token. `proxy.ts` refreshes auth cookies and redirects unauthenticated dashboard navigation.

## Backend

- `app/main.py`: application factory, middleware, health endpoint, and router registration
- `app/api/`: versioned HTTP route handlers
- `app/models.py`: SQLAlchemy domain models
- `app/schemas.py`: Pydantic request and response contracts
- `app/database.py`: engine, session factory, and request-scoped database dependency
- `app/errors.py`: consistent error envelopes
- `app/auth.py`: Supabase JWT verification and authenticated-user dependency
- `app/services/quotas.py`: durable usage reservations and per-user limits
- `app/services/legacy_ownership.py`: explicit operator-controlled ownership claims
- `app/services/storage.py`: private R2 S3-compatible operations and presigning
- `app/services/media_probe.py`: strict FFprobe subprocess and metadata parsing boundary
- `app/services/audio_preprocessing.py`: bounded FFmpeg speech-audio extraction and chunking
- `app/services/transcription.py`: provider-neutral Groq and optional CPU faster-whisper adapters
- `app/services/moment_discovery.py`: deterministic candidate generation, normalized scoring, deduplication, and provider-neutral Groq/fixture analyzers
- `app/services/clip_extraction.py`, `framing.py`, and `face_detection.py`: validated ranges and lightweight crop selection
- `app/services/subtitles.py`: clip-relative ASS captions from persisted transcript words
- `app/services/ffmpeg_commands.py`, `rendering.py`, and `export_validation.py`: safe command arrays, encoder fallback, progress, and output checks
- `app/services/export_storage.py`: private server-generated export keys, upload verification, and incomplete-object cleanup
- `app/services/youtube_import.py`: strict YouTube URL normalization and bounded, cookie-free yt-dlp adapter
- `app/worker.py`: PostgreSQL-claimed import, validation, transcription, moment, and render jobs with leases and retries
- `alembic/`: reviewed schema migrations

The project API is synchronous by design. The initial traffic profile does not benefit from an async database stack, and SQLAlchemy's small connection pool keeps the implementation and laptop resource use modest. The engine uses connection pre-ping, a three-connection base pool, and encrypted Supabase connections configured by URI.

## Data model

Milestone 2 preserves `Project` and adds:

- `MediaAsset`: sanitized original filename, private R2 key/bucket, declared size/type, verified media metadata, and validation status
- `UploadSession`: R2 upload ID, exact part size and expected size, lifecycle state, and expiry
- `ProcessingJob`: durable validation job, attempt limits, lease ownership, failure details, and timestamps
- `Transcript`: one idempotent transcript per asset with provider, model, language, lifecycle, and full text
- `TranscriptSegment` and `TranscriptWord`: validated absolute millisecond timestamps and optional confidence
- `MomentAnalysisRun`: reproducible provider/model/prompt/analysis settings, lifecycle, errors, and available token usage
- `MomentCandidate`: ranked recommendation, original AI boundaries, editable boundaries/title, factor breakdown, rationale, uncertainty, and review state
- `ClipExport`: approved moment, immutable render settings, lifecycle, private R2 key, codecs, duration, and output size
- `UserUsage` and `UserMonthlyUsage`: current reserved storage and monthly cost counters
- `YouTubeImport`: permission timestamp, canonical source identity, provenance metadata, reservation state, lifecycle, and errors

Projects and every private descendant carry a denormalized `owner_id` for direct, index-backed authorization checks. Existing pre-auth rows deliberately remain NULL until explicitly claimed.

Object keys are generated by the backend as `projects/{project_uuid}/originals/{asset_uuid}.{extension}` and `projects/{project_uuid}/exports/{export_uuid}.mp4`. Browser requests never choose a bucket, key, filesystem path, or R2 upload ID.

## Storage boundary

The relational database lives in Supabase. When the Supabase project is shared with another application, Howlix uses only the dedicated `howlix` PostgreSQL schema and keeps its Alembic version table there. Runtime connections restrict `search_path` to that schema. Original videos live only in the separate private `howlix-media` R2 bucket; another product's bucket or object prefix is never reused. The worker downloads one object at a time into a system-controlled temporary directory and removes it in a `finally`-equivalent context cleanup. `storage/` remains ignored and is not durable media storage.

## Security boundary

Supabase email/password Auth establishes identity. FastAPI validates JWT signature, issuer, audience, expiry, subject, and authenticated role, then applies owner filters before data access or R2 signing. Cross-user identifiers return 404. PostgreSQL counters enforce per-user beta limits independently of the in-process burst limiter. Signed URLs expire quickly and actual media type is verified by FFprobe rather than trusting the browser MIME type.

This remains a private-beta boundary, not a production security certification. Keep an identity-aware edge allowlist until security review, audit logging, dependency remediation, distributed throttling, and incident procedures are complete. See [security-model.md](security-model.md).

The database password and R2 API credentials stay in root `.env` and are used only by FastAPI/Alembic/the worker. Presigned URLs are temporary bearer tokens scoped to one operation, object key, upload ID, and part number.

## YouTube import boundary

Import requests reserve storage before queuing, accept only exact YouTube hosts and single-video routes, and require an explicit permission assertion. The worker never accepts browser cookies, account passwords, arbitrary downloader options, or client-selected object keys. It downloads one source into bounded temporary storage, enforces time/byte/duration limits, probes media before upload, verifies the server-generated private R2 object with `HeadObject`, and then queues the existing validation workflow. Terminal failures and cancellation clean incomplete objects and release durable reservations.

Automated tests deliberately use a temporary SQLite database and mocked transcription/moment providers. This keeps the suite fast, deterministic, and free of cloud writes or Groq calls; application runtime and migrations target Supabase Postgres. Explicit integration tests remain opt-in. Transcript text is not logged in full by default, and the LLM receives no video binary or R2 URL.

## Processing boundaries

Moment analysis and clip rendering use the same persisted job boundary as validation and transcription. Jobs carry non-null ownership and the worker refuses ownerless or inconsistent resource graphs. Rendering snapshots approved boundaries and settings, downloads one source into an isolated temporary directory, generates ASS captions from real word timestamps, and invokes FFmpeg without a shell. Machine-readable FFmpeg output persists actual encoded time. A working `h264_nvenc` is preferred; a probe or render failure falls back to bounded-thread `libx264`. The worker validates dimensions, codecs, duration, and size before uploading, verifies R2 with `HeadObject`, and always cleans its temporary directory. The worker remains intentionally sequential for the 8 GB development machine. Wider deployment still needs distributed abuse throttling, observability, and a managed worker runtime.

