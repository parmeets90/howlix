# YouTube URL imports

Howlix can import a single public YouTube video that the signed-in user owns or has explicit permission to download and process. This is an ingestion convenience, not a mechanism for bypassing YouTube or third-party rights.

## Installation on Windows

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
yt-dlp --version
ffmpeg -version
ffprobe -version
alembic upgrade head
python -m app.worker
```

Configuration:

```dotenv
YOUTUBE_IMPORT_ENABLED=true
YOUTUBE_IMPORT_MAX_BYTES=1073741824
YOUTUBE_IMPORT_TIMEOUT_SECONDS=900
YOUTUBE_IMPORT_MAX_CONCURRENT_PER_USER=1
YOUTUBE_IMPORT_MAX_RETRIES=3
```

The effective size ceiling is the smaller of `YOUTUBE_IMPORT_MAX_BYTES` and `MAX_UPLOAD_SIZE_MB`. Existing project/per-user storage quotas and `MAX_VIDEO_DURATION_SECONDS` also apply.

## Security and lifecycle

- Only exact `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be` hosts are accepted.
- Supported paths are `/watch?v=...`, `/shorts/...`, `/live/...`, and one youtu.be identifier.
- Credentials, custom ports, playlists, arbitrary hosts, and internal/private destinations are rejected before a job exists.
- The worker does not receive browser cookies, passwords, or authenticated YouTube sessions.
- No DRM, age gate, geographic restriction, login requirement, or platform protection is bypassed.
- Storage is reserved before queuing. The worker uses an isolated temporary directory, enforces byte/time/duration limits, probes with FFprobe, uploads to a server-generated private R2 key, verifies with `HeadObject`, and queues existing validation.
- Cancellation and terminal failure release reservations and clean incomplete objects. `(owner, project, video ID)` uniqueness prevents duplicate imports during retries.

## Maintenance and limitations

YouTube changes can break downloaders without a Howlix code change. Review and update `yt-dlp` regularly, rerun the importer tests, and live-test only a source you own or have permission to process. The supported range starts at the current stable PyPI release verified on 31 October 2026. Do not enable unattended package self-updates in the worker.

Ordinary tests use a deterministic fixture downloader and no external media. If a source is private, restricted, unavailable, or unsupported, use the unchanged manual multipart uploader.
