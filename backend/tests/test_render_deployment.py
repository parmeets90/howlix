from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def test_render_blueprint_is_free_api_only() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "plan: free" in blueprint
    assert "rootDir: backend" in blueprint
    assert "requirements-api.txt" in blueprint
    assert "app.main:app" in blueprint
    assert "--host 0.0.0.0" in blueprint
    assert "--port $PORT" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "app.worker" not in blueprint
    assert "alembic upgrade" not in blueprint
    assert "databases:" not in blueprint


def test_api_boot_does_not_import_worker_only_packages() -> None:
    check = """
import sys
import app.main

forbidden = {
    "cv2",
    "faster_whisper",
    "groq",
    "mediapipe",
    "torch",
    "yt_dlp",
}
loaded = sorted(name for name in forbidden if name in sys.modules)
if loaded:
    raise SystemExit(f"worker-only packages imported during API boot: {loaded}")
"""
    result = subprocess.run(
        [sys.executable, "-c", check],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_render_api_dependencies_cover_github_dispatch() -> None:
    requirements = (BACKEND / "requirements-api.txt").read_text(encoding="utf-8").lower()
    assert "httpx" in requirements
    dispatcher = (BACKEND / "app/services/github_dispatch.py").read_text(encoding="utf-8")
    assert "generate_get_url" not in dispatcher
