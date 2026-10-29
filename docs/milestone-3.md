# Milestone 3 — Reliable transcription

Milestone 3 adds durable, provider-neutral transcription on top of the verified Milestone 2 ingestion pipeline. It does not add hook scoring, clip selection, rendering, billing, or authentication.

## Processing flow

1. A ready media asset is queued through `POST /api/v1/media/{asset_id}/transcribe`.
2. Supabase stores one idempotent transcript and one `transcribe_media` job per asset.
3. The existing single worker claims the job with `FOR UPDATE SKIP LOCKED` and a renewable lease.
4. The worker downloads the private R2 object into a controlled temporary directory.
5. FFmpeg extracts 16 kHz mono FLAC chunks. Chunks overlap by one second and remain below the configured provider limit.
6. The selected provider returns original-language segment and word timestamps.
7. Absolute timestamps are restored, overlap duplicates are removed, and transcript rows are committed atomically.
8. Temporary source and audio files are removed when the temporary directory closes.

Actual stages and completed/total chunk counts are persisted. The UI does not invent progress percentages while a provider request is opaque.

## Providers

Groq is the default:

```dotenv
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

The key is backend-only. Requests use `verbose_json`, original-language transcription, and both `segment` and `word` timestamp granularities. HTTP 429 and 5xx failures receive bounded exponential retries; authentication and invalid-input failures are permanent.

The optional local fallback uses CPU INT8 and is intentionally not installed with the lightweight default environment:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-local-transcription.txt
```

Then set:

```dotenv
TRANSCRIPTION_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL=base
```

The first local run downloads the model and uses more RAM and disk than Groq. CUDA is not required.

## Database revision

Revision `20261029_0003` adds:

- `transcripts`
- `transcript_segments`
- `transcript_words`
- `progress_stage`, `progress_completed`, and `progress_total` on `processing_jobs`

The migration is additive and leaves existing project, media, upload, and validation records intact.

## API and interface

- `POST /api/v1/media/{asset_id}/transcribe`
- `GET /api/v1/media/{asset_id}/transcript`
- `GET /api/v1/media/{asset_id}/transcription-status`

Ready media cards expose a Transcribe Video action, real job stages, retry errors, transcript search, timestamped segments, and click-to-seek video navigation.

## Tests

Ordinary tests mock Groq and never call a paid API. They cover timestamps, chunk offsets, overlap deduplication, rate limits, permanent failures, empty speech, job retry/idempotency, persistence, temporary cleanup, API responses, and transcript filtering.

An optional live Groq test runs only when explicitly enabled:

```powershell
$env:RUN_GROQ_INTEGRATION_TESTS="true"
$env:GROQ_INTEGRATION_AUDIO_PATH="C:\path\to\small-speech.flac"
python -m pytest -m integration tests\test_groq_integration.py
```

## Limitations

- `GROQ_API_KEY` must be configured before cloud transcription can be queued.
- Local faster-whisper is optional and may be slow on the target laptop.
- One worker handles validation and transcription sequentially.
- There is no speaker diarization or transcript editing yet.
- The application remains single-user and must not be publicly exposed without an access gate.
