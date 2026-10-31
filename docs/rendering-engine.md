# Rendering engine

## FFmpeg setup and encoder checks

```powershell
winget install --id Gyan.FFmpeg --exact
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -encoders | Select-String "h264_nvenc|libx264"
ffmpeg -hide_banner -filters | Select-String "ass"
```

Listing `h264_nvenc` does not prove the GPU and driver can encode. Howlix performs a tiny real encode probe. If that probe or the actual NVENC render fails, it retries once with `libx264`. The verified development laptop used libx264 because the NVENC probe failed.

```dotenv
RENDER_TIMEOUT_SECONDS=1200
RENDER_CPU_THREADS=2
RENDER_PREFER_NVENC=true
RENDER_FPS_CAP=30
RENDER_MAX_OUTPUT_MB=500
```

Only one render job may be active. FFmpeg receives an argument array with `shell=False`, accurate input seek plus duration, explicit crop/scale, `setsar=1`, source-aware FPS capped by configuration, `yuv420p`, H.264, optional AAC, and `+faststart`.

## Framing

- **Center:** stable aspect-correct crop and the universal fallback.
- **Face:** optional OpenCV Haar detection samples at low frequency, combines visible faces, and uses a median focus to avoid jitter. Install with `python -m pip install -r requirements-face-detection.txt`.
- **Manual:** normalized X/Y focus values from 0 through 1, clamped so the crop always remains inside the frame.

The renderer supports 9:16, 1:1, and 16:9 at a 720 or 1080 quality tier. It never stretches the source.

## Inspecting an export

```powershell
ffprobe -v error -show_streams -show_format "C:\path\to\export.mp4"
ffmpeg -hide_banner -ss 00:00:05 -i "C:\path\to\export.mp4" -frames:v 1 "C:\path\to\frame.png"
```

Check that dimensions match, sample aspect ratio is `1:1`, video is H.264/yuv420p, audio is AAC when present, captions stay inside safe margins, and speech remains synchronized near both ends.

## Common failures

- `No such filter: ass`: install a full FFmpeg build with libass.
- NVENC initialization error: leave fallback enabled or set `RENDER_PREFER_NVENC=false`.
- Missing glyphs: install Noto Sans and use Nirmala UI for Hindi/Punjabi; restart the worker after changes.
- Timeout: raise `RENDER_TIMEOUT_SECONDS` cautiously or use 720p; do not increase concurrent renders on an 8 GB machine.
- R2 upload/HeadObject failure: the job retries and removes incomplete export objects.
- Stuck processing after a crash: the PostgreSQL lease expires and another worker safely reclaims the job.
