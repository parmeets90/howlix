from __future__ import annotations

import math
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class AudioPreprocessingError(RuntimeError):
    """The source cannot be converted into supported speech audio."""


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset_ms: int
    duration_ms: int


ProgressCallback = Callable[[int, int], None]


def extract_audio_chunks(
    source: Path,
    output_directory: Path,
    *,
    duration_seconds: float,
    ffmpeg_path: str,
    timeout_seconds: int,
    chunk_seconds: int,
    overlap_seconds: float,
    max_chunk_bytes: int,
    progress: ProgressCallback | None = None,
) -> list[AudioChunk]:
    if duration_seconds <= 0:
        raise AudioPreprocessingError("The video has no usable duration.")
    output_directory.mkdir(parents=True, exist_ok=True)
    step = chunk_seconds - overlap_seconds
    total = max(1, math.ceil(max(0.0, duration_seconds - overlap_seconds) / step))
    chunks: list[AudioChunk] = []

    for index in range(total):
        start = index * step
        remaining = duration_seconds - start
        if remaining <= 0:
            break
        length = min(float(chunk_seconds), remaining)
        output = output_directory / f"audio-{index:04d}.flac"
        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{length:.3f}",
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            "-y",
            str(output),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioPreprocessingError("FFmpeg audio extraction timed out.") from exc
        except OSError as exc:
            raise AudioPreprocessingError("FFmpeg could not be started.") from exc
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            raise AudioPreprocessingError(
                "The video has no supported audio stream or audio extraction failed."
            )
        if output.stat().st_size > max_chunk_bytes:
            raise AudioPreprocessingError(
                "A speech-audio chunk exceeds the configured provider file-size limit. "
                "Reduce TRANSCRIPTION_CHUNK_SECONDS and retry."
            )
        chunks.append(
            AudioChunk(
                path=output,
                offset_ms=round(start * 1000),
                duration_ms=round(length * 1000),
            )
        )
        if progress is not None:
            progress(index + 1, total)

    if not chunks:
        raise AudioPreprocessingError("The video did not produce any speech-audio chunks.")
    return chunks
