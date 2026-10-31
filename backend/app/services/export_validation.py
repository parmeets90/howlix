from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.media_probe import MediaProbeResult, MediaValidationError, probe_media


class ExportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedExport:
    metadata: MediaProbeResult
    file_size_bytes: int


def validate_export(
    path: Path,
    *,
    ffprobe_path: str,
    timeout_seconds: int,
    expected_duration_ms: int,
    expected_width: int,
    expected_height: int,
    expected_audio: bool,
    maximum_size_bytes: int,
) -> ValidatedExport:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ExportValidationError("Rendered output could not be read.") from exc
    if size <= 0 or size > maximum_size_bytes:
        raise ExportValidationError("Rendered output size is invalid or exceeds the configured limit.")
    try:
        metadata = probe_media(
            path,
            ffprobe_path,
            timeout_seconds,
            max(2, expected_duration_ms // 1000 + 3),
        )
    except MediaValidationError as exc:
        raise ExportValidationError(str(exc)) from exc
    if (metadata.width, metadata.height) != (expected_width, expected_height):
        raise ExportValidationError("Rendered output dimensions do not match the request.")
    if metadata.video_codec != "h264":
        raise ExportValidationError("Rendered output is not H.264 video.")
    if expected_audio and metadata.audio_codec != "aac":
        raise ExportValidationError("Rendered output audio is missing or not AAC.")
    if abs(round(metadata.duration_seconds * 1000) - expected_duration_ms) > 1500:
        raise ExportValidationError("Rendered output duration does not match the approved moment.")
    return ValidatedExport(metadata, size)
