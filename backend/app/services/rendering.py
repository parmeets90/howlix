from __future__ import annotations

import os
import queue
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from threading import Thread
from typing import Callable

from app.services.ffmpeg_commands import RenderCommandOptions, build_ffmpeg_render_command


class RenderError(RuntimeError):
    pass


class RenderCancelled(RenderError):
    pass


class RenderTimeout(RenderError):
    pass


ProgressCallback = Callable[[int, int], None]
CancellationCheck = Callable[[], bool]


@lru_cache(maxsize=4)
def nvenc_is_working(ffmpeg_path: str) -> bool:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=size=128x128:rate=1:duration=0.1",
        "-frames:v",
        "1",
        "-c:v",
        "h264_nvenc",
        "-f",
        "null",
        os.devnull,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def select_encoder(ffmpeg_path: str, prefer_nvenc: bool) -> str:
    return "h264_nvenc" if prefer_nvenc and nvenc_is_working(ffmpeg_path) else "libx264"


def _terminate(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    duration_ms: int,
    timeout_seconds: int,
    progress: ProgressCallback,
    cancelled: CancellationCheck,
) -> None:
    stderr_path = cwd / "ffmpeg-error.log"
    started = time.monotonic()
    line_queue: queue.Queue[str | None] = queue.Queue()
    with stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except FileNotFoundError as exc:
            raise RenderError("FFmpeg was not found. Configure FFMPEG_PATH.") from exc
        except OSError as exc:
            raise RenderError("FFmpeg could not be started.") from exc

        def read_progress() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                line_queue.put(line.rstrip())
            line_queue.put(None)

        reader = Thread(target=read_progress, daemon=True, name="howlix-ffmpeg-progress")
        reader.start()
        progress_value = 0
        while True:
            if cancelled():
                _terminate(process)
                raise RenderCancelled("Clip export was cancelled.")
            if time.monotonic() - started > timeout_seconds:
                _terminate(process)
                raise RenderTimeout("FFmpeg render timed out.")
            try:
                line = line_queue.get(timeout=0.25)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                break
            key, separator, value = line.partition("=")
            if not separator:
                continue
            if key in {"out_time_us", "out_time_ms"}:
                try:
                    progress_value = min(duration_ms, max(progress_value, int(value) // 1000))
                    progress(progress_value, duration_ms)
                except ValueError:
                    pass
        return_code = process.wait()
        reader.join(timeout=1)

    if return_code != 0:
        error_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RenderError(f"FFmpeg render failed: {error_tail or 'unknown encoder error'}")
    progress(duration_ms, duration_ms)


def render_with_fallback(
    options: RenderCommandOptions,
    *,
    timeout_seconds: int,
    progress: ProgressCallback,
    cancelled: CancellationCheck,
) -> str:
    encoders = [options.encoder]
    if options.encoder == "h264_nvenc":
        encoders.append("libx264")
    last_error: RenderError | None = None
    for encoder in encoders:
        if options.output.exists():
            options.output.unlink()
        candidate = RenderCommandOptions(**{**options.__dict__, "encoder": encoder})
        try:
            _run_command(
                build_ffmpeg_render_command(candidate),
                cwd=options.output.parent,
                duration_ms=options.clip.duration_ms,
                timeout_seconds=timeout_seconds,
                progress=progress,
                cancelled=cancelled,
            )
            return encoder
        except (RenderCancelled, RenderTimeout):
            raise
        except RenderError as exc:
            last_error = exc
    raise last_error or RenderError("No usable H.264 encoder was available.")
