from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.export_validation import validate_export
from app.services.storage import R2StorageService
from app.worker import MediaValidationWorker


pytestmark = pytest.mark.integration


def test_real_approved_moment_renders_and_round_trips_through_private_r2(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    if not settings.run_render_integration_tests:
        pytest.skip("Set RUN_RENDER_INTEGRATION_TESTS=true to permit a real render and R2 write.")
    moment_id = os.getenv("RENDER_INTEGRATION_MOMENT_ID")
    if not moment_id:
        pytest.skip("Set RENDER_INTEGRATION_MOMENT_ID to an approved moment UUID.")
    settings.require_r2()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/moments/{moment_id}/exports",
            json={
                "aspect_ratio": "9:16",
                "quality": "720p",
                "framing_mode": "center",
                "caption_preset": "bold",
            },
        )
        assert response.status_code == 202, response.text
        export = response.json()
        if export["status"] != "completed":
            worker = MediaValidationWorker(settings, R2StorageService(settings))
            assert worker.run_once() is True
            export = client.get(f"/api/v1/exports/{export['id']}").json()
        assert export["status"] == "completed", export

        download = client.get(f"/api/v1/exports/{export['id']}/download")
        assert download.status_code == 200, download.text
        output = tmp_path / "howlix-real-export.mp4"
        with httpx.stream("GET", download.json()["url"], timeout=120) as stream:
            stream.raise_for_status()
            with output.open("wb") as file_handle:
                for chunk in stream.iter_bytes():
                    file_handle.write(chunk)

    validated = validate_export(
        output,
        ffprobe_path=settings.ffprobe_path,
        timeout_seconds=settings.ffprobe_timeout_seconds,
        expected_duration_ms=export["duration_ms"],
        expected_width=720,
        expected_height=1280,
        expected_audio=export["audio_codec"] is not None,
        maximum_size_bytes=settings.render_max_output_bytes,
    )
    assert validated.file_size_bytes == export["file_size_bytes"]
    probe = subprocess.run(
        [
            settings.ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=sample_aspect_ratio,display_aspect_ratio",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=settings.ffprobe_timeout_seconds,
        check=True,
    )
    video_stream = json.loads(probe.stdout)["streams"][0]
    assert video_stream["sample_aspect_ratio"] == "1:1"
    assert video_stream["display_aspect_ratio"] == "9:16"
