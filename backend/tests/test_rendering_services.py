from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import ClipExportCreateRequest
from app.services.clip_extraction import (
    ClipBoundaryError,
    ClipRange,
    clip_relative_words,
    validate_clip_range,
)
from app.services.export_validation import validate_export
from app.services.ffmpeg_commands import RenderCommandOptions, build_ffmpeg_render_command
from app.services.framing import (
    FaceBox,
    FaceObservation,
    calculate_crop,
    output_dimensions,
    stable_face_focus,
)
from app.services.media_probe import probe_media
from app.services.rendering import RenderError, render_with_fallback
from app.services.subtitles import CaptionStyle, ass_escape, build_ass_document, choose_font, write_ass_file


def test_clip_boundaries_and_relative_word_timestamps() -> None:
    clip = validate_clip_range(10_000, 40_000, source_duration_ms=60_000)
    words = [
        SimpleNamespace(start_ms=9_500, end_ms=10_500, word="Hello"),
        SimpleNamespace(start_ms=20_000, end_ms=21_000, word="दुनिया"),
        SimpleNamespace(start_ms=40_000, end_ms=41_000, word="outside"),
    ]
    relative = clip_relative_words(words, clip)
    assert [(item.start_ms, item.end_ms, item.word) for item in relative] == [
        (0, 500, "Hello"),
        (10_000, 11_000, "दुनिया"),
    ]
    with pytest.raises(ClipBoundaryError):
        validate_clip_range(30_000, 70_000, source_duration_ms=60_000)


def test_empty_and_multilingual_ass_captions_are_safe() -> None:
    style = CaptionStyle("karaoke", 52, "#FFFFFF", "#A78BFA", "bottom")
    assert build_ass_document(
        [], width=720, height=1280, style=style, latin_font="Noto Sans", complex_font="Nirmala UI"
    ) == ""
    document = build_ass_document(
        [
            SimpleNamespace(start_ms=0, end_ms=500, word="कैसे"),
            SimpleNamespace(start_ms=600, end_ms=1200, word="सीखें{अब}"),
            SimpleNamespace(start_ms=1300, end_ms=1800, word="ਪੰਜਾਬੀ"),
        ],
        width=720,
        height=1280,
        style=style,
        latin_font="Noto Sans",
        complex_font="Nirmala UI",
    )
    assert "Nirmala UI" in document
    assert r"\k50" in document
    assert r"\{" in document and r"\}" in document
    assert "कैसे" in document and "ਪੰਜਾਬੀ" in document
    assert ass_escape("line\n{tag}") == r"line\N\{tag\}"
    assert choose_font("हिन्दी", latin_font="", complex_font="") == "Nirmala UI"
    assert choose_font("English", latin_font="", complex_font="") == "Arial"


def test_crop_math_center_manual_no_face_and_multiple_faces() -> None:
    assert output_dimensions("9:16", "720p") == (720, 1280)
    center = calculate_crop(1920, 1080, 720, 1280)
    assert center.height == 1080
    assert center.width % 2 == 0
    assert center.x > 0
    left = calculate_crop(1920, 1080, 720, 1280, focus_x=0, focus_y=0.5)
    assert left.x == 0
    assert stable_face_focus([]) is None
    focus = stable_face_focus(
        [
            FaceObservation(0, (FaceBox(0.1, 0.2, 0.2, 0.3), FaceBox(0.7, 0.2, 0.2, 0.3))),
            FaceObservation(1000, (FaceBox(0.45, 0.2, 0.2, 0.3),)),
        ]
    )
    assert focus is not None
    assert 0.45 <= focus[0] <= 0.55


def test_manual_crop_validation() -> None:
    request = ClipExportCreateRequest(
        framing_mode="manual", manual_crop_x=0.25, manual_crop_y=0.5
    )
    assert request.manual_crop_x == 0.25
    with pytest.raises(ValidationError):
        ClipExportCreateRequest(framing_mode="manual")
    with pytest.raises(ValidationError):
        ClipExportCreateRequest(framing_mode="center", manual_crop_x=0.2, manual_crop_y=0.5)


def _options(tmp_path: Path, *, encoder: str = "libx264", captions: str | None = None):
    return RenderCommandOptions(
        ffmpeg_path="ffmpeg",
        source=tmp_path / "source;safe.mp4",
        output=tmp_path / "output.mp4",
        clip=ClipRange(500, 3000),
        crop=calculate_crop(640, 360, 720, 1280),
        output_width=720,
        output_height=1280,
        fps=30,
        encoder=encoder,
        cpu_threads=2,
        has_audio=True,
        captions_filename=captions,
        fonts_dir=Path("C:/Windows/Fonts"),
    )


def test_ffmpeg_command_is_argument_safe(tmp_path: Path) -> None:
    command = build_ffmpeg_render_command(_options(tmp_path))
    assert isinstance(command, list)
    assert str(tmp_path / "source;safe.mp4") in command
    assert "shell=True" not in command
    assert command[command.index("-ss") + 1] == "0.500"
    assert command[command.index("-t") + 1] == "2.500"
    assert "setsar=1" in command[command.index("-vf") + 1]
    assert "+faststart" in command


def test_nvenc_failure_retries_with_libx264(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "h264_nvenc" in command:
            raise RenderError("NVENC unavailable")
        Path(command[-1]).write_bytes(b"mp4")
        kwargs["progress"](kwargs["duration_ms"], kwargs["duration_ms"])

    monkeypatch.setattr("app.services.rendering._run_command", fake_run)
    encoder = render_with_fallback(
        _options(tmp_path, encoder="h264_nvenc"),
        timeout_seconds=30,
        progress=lambda _completed, _total: None,
        cancelled=lambda: False,
    )
    assert encoder == "libx264"
    assert len(calls) == 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_real_ffmpeg_render_preserves_duration_audio_and_vertical_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    create = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=4",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(source),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert create.returncode == 0, create.stderr.decode(errors="replace")
    captions = build_ass_document(
        [SimpleNamespace(start_ms=0, end_ms=700, word="Hello"), SimpleNamespace(start_ms=800, end_ms=1500, word="दुनिया")],
        width=720,
        height=1280,
        style=CaptionStyle("bold", 52, "#FFFFFF", "#A78BFA", "bottom"),
        latin_font="Noto Sans",
        complex_font="Nirmala UI",
    )
    write_ass_file(tmp_path / "captions.ass", captions)
    options = RenderCommandOptions(
        **{
            **_options(tmp_path, captions="captions.ass").__dict__,
            "source": source,
        }
    )
    encoder = render_with_fallback(
        options,
        timeout_seconds=120,
        progress=lambda _completed, _total: None,
        cancelled=lambda: False,
    )
    assert encoder == "libx264"
    validated = validate_export(
        options.output,
        ffprobe_path="ffprobe",
        timeout_seconds=30,
        expected_duration_ms=2500,
        expected_width=720,
        expected_height=1280,
        expected_audio=True,
        maximum_size_bytes=50 * 1024 * 1024,
    )
    assert validated.metadata.audio_codec == "aac"
    assert validated.metadata.video_codec == "h264"
    assert abs(validated.metadata.duration_seconds - 2.5) < 0.2
