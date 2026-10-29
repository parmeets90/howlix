# Milestone 2: reliable video ingestion

## Outcome

Milestone 2 adds a complete private-media ingestion path without introducing a local database server, Docker, Redis, or a heavyweight queue. Supabase Postgres remains the runtime database. Cloudflare R2 holds original video objects. A single local worker downloads one object at a time for FFprobe validation.

The application is still a single-user localhost development environment. It has no authentication or tenant authorization and must not be exposed publicly.

## Upload flow

1. The browser creates a project through FastAPI.
2. The browser declares the filename, MIME type, and exact byte size to the initiate endpoint.
3. FastAPI validates the declaration, generates a UUID-based object key, creates an R2 multipart upload, and persists an asset and upload session.
4. The browser requests a presigned URL for each exact part number and uploads 16 MiB file slices directly to R2, with at most two requests in flight.
5. The browser sends ordered part numbers and ETags to FastAPI.
6. FastAPI compares them with R2 `ListParts`, completes the multipart upload, verifies the object and final size with `HeadObject`, and creates one validation job.
7. The local worker claims the job with PostgreSQL `FOR UPDATE SKIP LOCKED`, downloads the object to a temporary directory, runs FFprobe, persists verified metadata, and removes the temporary file.
8. The project page polls persisted media status. Ready media receives a short-lived signed GET URL for preview.

Video bytes do not pass through FastAPI and are never stored in PostgreSQL.

## Persisted entities

- `media_assets`: private storage location, sanitized display filename, declared size/type, verified media metadata, state, and validation error.
- `upload_sessions`: R2 multipart upload ID, part size, expected size, expiry, and lifecycle state.
- `processing_jobs`: validation job state, retries, lease ownership, lease expiry, and failure detail.

The worker can reclaim a processing job after its lease expires. Job state is never kept only in memory.

## Status behavior

- Asset: `pending_upload`, `uploading`, `uploaded`, `validating`, `ready`, `rejected`, `failed`, or `aborted`.
- Upload session: `initiated`, `uploading`, `completed`, `aborted`, `expired`, or `failed`.
- Job: `queued`, `processing`, `succeeded`, or `failed`.

An unsupported, corrupted, or over-duration video is a successful validation job whose asset is `rejected`. Transient storage and process failures are retried until the configured job attempt limit is reached.

## Browser recovery

The frontend stores only non-secret session metadata in `localStorage`: project/session IDs, filename, size, type, last modification time, and part size. It never stores R2 credentials or presigned URLs.

After refresh, browsers do not allow a web application to regain access to the original local `File`. The user must reselect the same file. The frontend verifies its identifying metadata, asks FastAPI/R2 which parts exist, and resumes only missing parts. A different file is rejected. Recovery is unavailable after the upload session expires or is aborted; the user must start a new upload.

## Limits and security boundaries

- Maximum declared and verified size: 1 GiB by default.
- Maximum verified duration: 30 minutes.
- One worker job at a time.
- 16 MiB multipart parts and two concurrent browser uploads.
- Short-lived signed URLs, private bucket, server-generated keys, and no arbitrary client-supplied bucket/key/upload ID.
- Per-project storage quota and local rate limits for initiate/sign operations.
- Browser MIME is only a preliminary check; FFprobe is authoritative.

The rate limiter is intentionally process-local for this single FastAPI development process. Public or multi-instance deployment requires authenticated authorization and a shared rate-limit service.

## Verification

Ordinary tests replace R2 with an in-memory mock. They cover multipart initiation, signing, completion, duplicate completion, cancellation, invalid/oversized input, size mismatch, storage failure, persistence, FFprobe rejection, job recovery, and temporary-file cleanup. Frontend tests exercise real XHR progress events and upload error states.

The real R2 integration test is skipped unless `RUN_R2_INTEGRATION_TESTS=true` and all R2 credentials are configured. It creates, completes, verifies, downloads, and deletes one small test object.

## Deferred work

Milestone 2 does not include authentication, public deployment, transcription, moment scoring, clip rendering, captions, billing, or a distributed queue. See [the roadmap](roadmap.md) for the next product stages.
