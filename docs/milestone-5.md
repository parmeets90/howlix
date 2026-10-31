# Milestone 5 - automatic clip exports

Milestone 5 turns an approved moment into a private, downloadable MP4. The render uses the moment's current reviewed boundaries; it never changes or overwrites the original R2 object.

## End-to-end flow

1. `POST /api/v1/moments/{moment_id}/exports` validates approval, boundaries, output limits, framing, and caption settings.
2. The API creates an idempotent `clip_exports` row and a leased `clip_render` job. FFmpeg never runs in the request handler.
3. The worker downloads the private original and verifies its byte size.
4. It selects center crop, normalized manual focus, or an optional low-frequency CPU face sample. Face detection failure falls back to center crop.
5. Transcript words are shifted by `word_time - clip_start`, clamped to the clip, escaped, and written to ASS.
6. FFmpeg accurately seeks and re-encodes the interval, crops without stretching, sets square pixels, burns captions, and reports encoded time through `-progress pipe:1`.
7. FFprobe validates H.264, optional AAC, dimensions, duration, and output size.
8. The worker uploads to `projects/{project_id}/exports/{export_id}.mp4`, verifies `HeadObject`, and commits completion metadata.
9. The frontend requests a short-lived private URL for preview or download.

## Database and API

Alembic revision `20261030_0005` adds `clip_exports` and links one render job to an export without changing prior media, transcripts, or recommendations.

- `POST /api/v1/moments/{moment_id}/exports`
- `GET /api/v1/moments/{moment_id}/exports`
- `GET /api/v1/exports/{export_id}`
- `GET /api/v1/exports/{export_id}/download`
- `POST /api/v1/exports/{export_id}/cancel`

Only approved moments export by default. Render settings are server-validated and fingerprinted; clients cannot provide paths or R2 keys. Repeating the same completed request returns the existing export.

## Windows startup

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

In a second window:

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

In a third window:

```powershell
cd "D:\Claude Code Projects\howlix\frontend"
npm run dev
```

Approve a recommendation, choose **Create Clip**, select settings, and start the render. The UI shows persisted stages and encoded milliseconds, then reveals the real finished preview and download action.

## Optional real integration test

```powershell
$env:RUN_RENDER_INTEGRATION_TESTS="true"
$env:RENDER_INTEGRATION_MOMENT_ID="approved-moment-uuid"
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m pytest -m integration tests\test_render_integration.py -s
```

This test incurs real bandwidth, CPU/GPU work, and R2 writes. It verifies the signed download, codecs, duration, dimensions, square pixels, and exact 9:16 display ratio.

## Limits

- Face-aware mode is lightweight guidance, not perfect speaker tracking. OpenCV is optional and center crop is the reliable fallback.
- Caption placement does not yet move dynamically around faces.
- Cancellation is cooperative and may take a progress polling interval to stop FFmpeg.
- Finished clips are recommendations rendered from approved boundaries, not evidence of predicted virality.
- The app is single-user and unauthenticated; keep it private.
