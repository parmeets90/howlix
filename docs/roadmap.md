# Product roadmap

## Milestone 1 — Development foundation

Status: implemented in this repository.

- Branded landing page and project workspace
- FastAPI project endpoints and Supabase Postgres persistence
- Local file selection UI
- Automated API tests and development documentation

## Milestone 2 — Reliable video ingestion

Status: implemented in this repository.

- Direct browser-to-private-R2 multipart upload; FastAPI never proxies video bytes
- Server-controlled UUID object keys, declared input limits, and private signed previews
- Persisted upload sessions, media assets, and lease-backed processing jobs in Supabase
- FFprobe validation, verified metadata, duration limits, and invalid-object cleanup
- True byte progress, pause, resume, cancellation, retry, and refresh reconciliation
- Mocked R2/worker tests plus an explicit opt-in real R2 integration test

Milestone 2 establishes trustworthy ingestion before adding AI. Redis, RQ, transcription, and public deployment remain out of scope unless workload measurements justify them.

## Milestone 3 — Transcription foundation

Status: implemented in this repository.

- Provider-neutral transcription interface
- Optional faster-whisper local adapter and Groq cloud adapter
- Timestamped transcript segments and transcript viewer
- Job status and retry semantics
- FFmpeg audio chunking, overlap deduplication, word timestamps, search, and video seeking

## Milestone 4 — Moment discovery

Status: implemented in this repository.

- Structured hook and moment analysis
- Transparent editorial score factors
- Candidate clip review and manual boundary adjustment
- Evaluation set for recommendation quality

## Milestone 5 — Short rendering

Status: implemented in this repository.

- Vertical layouts and FFmpeg rendering
- Caption styling through libass
- Lightweight face-aware, stable center, and manual cropping
- Export history and downloadable outputs

The local worker renders one job at a time, prefers a working NVENC encoder, and falls back to bounded-thread libx264. Exports remain private in R2. Scene-aware cutting is deferred because approved moment boundaries already define the clip and automatic extra cuts could change editorial meaning.

## Milestone 6 — Editing and delivery refinement

- Better face tracking and multi-speaker composition controls
- Per-word caption editing and reusable brand presets
- Export quality comparison, thumbnails, and final editorial polish
- Authentication and authorization before any public access

## Later product work

Authentication, multi-tenancy, production worker hosting/queues, observability, subscriptions, and team collaboration belong after the core clipping workflow is proven.

