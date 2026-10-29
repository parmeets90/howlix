from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


SUPPORTED_FORMATS = {"mov", "mp4", "webm", "matroska"}
SUPPORTED_VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}
SUPPORTED_AUDIO_CODECS = {"aac", "opus", "vorbis", "mp3"}


class MediaValidationError(ValueError):
    """The downloaded object is not an acceptable video."""


class MediaProbeError(RuntimeError):
    """FFprobe could not be executed reliably and the job may be retried."""


@dataclass(frozen=True)
class MediaProbeResult:
    duration_seconds: float
    width: int
    height: int
    frame_rate: float | None
    video_codec: str
    audio_codec: str | None
    container_format: str


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _frame_rate(value: object) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        parsed = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return round(parsed, 4) if math.isfinite(parsed) and parsed > 0 else None


def parse_ffprobe_payload(payload: object, max_duration_seconds: int) -> MediaProbeResult:
    if not isinstance(payload, dict):
        raise MediaValidationError("FFprobe returned invalid metadata.")
    format_data = payload.get("format")
    streams = payload.get("streams")
    if not isinstance(format_data, dict) or not isinstance(streams, list):
        raise MediaValidationError("The file does not contain readable media metadata.")

    format_name = str(format_data.get("format_name", "")).lower()
    format_tokens = {token.strip() for token in format_name.split(",") if token.strip()}
    if not format_tokens.intersection(SUPPORTED_FORMATS):
        raise MediaValidationError("The actual video container is not MP4, MOV, or WebM.")

    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    if not isinstance(video_stream, dict):
        raise MediaValidationError("The file does not contain a video stream.")
    video_codec = str(video_stream.get("codec_name", "")).lower()
    if video_codec not in SUPPORTED_VIDEO_CODECS:
        raise MediaValidationError(f"Unsupported video codec: {video_codec or 'unknown'}.")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaValidationError("The video resolution is invalid.")

    duration = _positive_float(format_data.get("duration")) or _positive_float(
        video_stream.get("duration")
    )
    if duration is None:
        raise MediaValidationError("The video duration could not be determined.")
    if duration > max_duration_seconds:
        raise MediaValidationError(
            f"The video exceeds the {max_duration_seconds // 60}-minute duration limit."
        )

    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    audio_codec = None
    if isinstance(audio_stream, dict):
        audio_codec = str(audio_stream.get("codec_name", "")).lower() or None
        if audio_codec and audio_codec not in SUPPORTED_AUDIO_CODECS:
            raise MediaValidationError(f"Unsupported audio codec: {audio_codec}.")

    return MediaProbeResult(
        duration_seconds=round(duration, 3),
        width=width,
        height=height,
        frame_rate=_frame_rate(
            video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
        ),
        video_codec=video_codec,
        audio_codec=audio_codec,
        container_format=format_name,
    )


def probe_media(
    path: Path,
    ffprobe_path: str,
    timeout_seconds: int,
    max_duration_seconds: int,
) -> MediaProbeResult:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError(
            "FFprobe was not found. Install FFmpeg or configure FFPROBE_PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError("FFprobe timed out while inspecting the video.") from exc
    except OSError as exc:
        raise MediaProbeError("FFprobe could not be started.") from exc

    if result.returncode != 0:
        raise MediaValidationError("The uploaded file is corrupted or is not a valid video.")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaValidationError("FFprobe returned malformed video metadata.") from exc
    return parse_ffprobe_payload(payload, max_duration_seconds)

