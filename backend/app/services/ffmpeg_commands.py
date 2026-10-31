from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.clip_extraction import ClipRange
from app.services.framing import CropRect


@dataclass(frozen=True)
class RenderCommandOptions:
    ffmpeg_path: str
    source: Path
    output: Path
    clip: ClipRange
    crop: CropRect
    output_width: int
    output_height: int
    fps: float
    encoder: str
    cpu_threads: int
    has_audio: bool
    captions_filename: str | None = None
    fonts_dir: Path | None = None


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_video_filter(options: RenderCommandOptions) -> str:
    filters = [
        f"crop={options.crop.width}:{options.crop.height}:{options.crop.x}:{options.crop.y}",
        f"scale={options.output_width}:{options.output_height}:flags=lanczos",
        "setsar=1",
        f"fps={options.fps:g}",
        "format=yuv420p",
    ]
    if options.captions_filename:
        subtitle = f"ass=filename='{options.captions_filename}'"
        if options.fonts_dir:
            subtitle += f":fontsdir='{_filter_path(options.fonts_dir)}'"
        filters.append(subtitle)
    return ",".join(filters)


def build_ffmpeg_render_command(options: RenderCommandOptions) -> list[str]:
    command = [
        options.ffmpeg_path,
        "-hide_banner",
        "-y",
        "-ss",
        f"{options.clip.start_ms / 1000:.3f}",
        "-i",
        str(options.source),
        "-t",
        f"{options.clip.duration_ms / 1000:.3f}",
        "-map",
        "0:v:0",
    ]
    if options.has_audio:
        command += ["-map", "0:a:0?"]
    command += ["-vf", build_video_filter(options)]
    if options.encoder == "h264_nvenc":
        command += ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "22", "-b:v", "0"]
    elif options.encoder == "libx264":
        command += [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-threads",
            str(options.cpu_threads),
        ]
    else:
        raise ValueError("Unsupported H.264 encoder.")
    if options.has_audio:
        command += ["-c:a", "aac", "-b:a", "160k"]
    command += [
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-avoid_negative_ts",
        "make_zero",
        "-progress",
        "pipe:1",
        "-stats_period",
        "0.5",
        "-nostats",
        str(options.output),
    ]
    return command
