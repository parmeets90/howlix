from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select

from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    UserUsage,
    YouTubeImport,
    YouTubeImportStatus,
)
from app.config import get_settings
from app.services.media_probe import MediaProbeResult
from app.services.youtube_import import (
    DownloadedYouTubeVideo,
    validate_youtube_url,
)
from app.worker import MediaValidationWorker
from tests.conftest import SECOND_USER_ID, TEST_USER_ID


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_youtube_url_validation(url: str, video_id: str) -> None:
    validated = validate_youtube_url(url)
    assert validated.video_id == video_id
    assert validated.canonical_url == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/watch?v=dQw4w9WgXcQ",
        "http://169.254.169.254/latest/meta-data",
        "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
        "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com:8443/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
        "https://youtube.com/playlist?list=PL123",
    ],
)
def test_youtube_url_validation_blocks_ssrf_and_playlists(url: str) -> None:
    with pytest.raises(ValueError):
        validate_youtube_url(url)


def _project(session_factory, *, owner_id=TEST_USER_ID) -> uuid.UUID:
    project_id = uuid.uuid4()
    with session_factory() as db:
        db.add(Project(id=project_id, owner_id=owner_id, title="YouTube import"))
        db.commit()
    return project_id


def test_import_requires_permission_and_is_idempotent(client, testing_session_factory) -> None:
    project_id = _project(testing_session_factory)
    payload = {"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": False}
    assert client.post(f"/api/v1/projects/{project_id}/youtube-imports", json=payload).status_code == 422
    payload["permission_confirmed"] = True
    first = client.post(f"/api/v1/projects/{project_id}/youtube-imports", json=payload)
    second = client.post(f"/api/v1/projects/{project_id}/youtube-imports", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    with testing_session_factory() as db:
        assert len(list(db.scalars(select(YouTubeImport)))) == 1
        assert len(list(db.scalars(select(ProcessingJob)))) == 1


def test_cross_user_import_access_is_hidden(client, testing_session_factory) -> None:
    project_id = _project(testing_session_factory)
    response = client.post(
        f"/api/v1/projects/{project_id}/youtube-imports",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": True},
    )
    import_id = response.json()["id"]
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
        SECOND_USER_ID, "user-b@example.test", "authenticated"
    )
    assert client.get(f"/api/v1/youtube-imports/{import_id}").status_code == 404
    assert client.post(f"/api/v1/youtube-imports/{import_id}/cancel").status_code == 404


def test_import_can_be_cancelled_and_releases_reservation(client, testing_session_factory) -> None:
    project_id = _project(testing_session_factory)
    created = client.post(
        f"/api/v1/projects/{project_id}/youtube-imports",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": True},
    ).json()
    cancelled = client.post(f"/api/v1/youtube-imports/{created['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    with testing_session_factory() as db:
        usage = db.get(UserUsage, TEST_USER_ID)
        asset = db.get(MediaAsset, uuid.UUID(created["asset_id"]))
        assert usage is not None and usage.stored_media_bytes == 0
        assert asset is not None and asset.status == MediaAssetStatus.ABORTED


def test_import_enforces_durable_storage_quota(client, testing_session_factory) -> None:
    project_id = _project(testing_session_factory)
    settings = get_settings()
    with testing_session_factory() as db:
        db.add(
            UserUsage(
                owner_id=TEST_USER_ID,
                stored_media_bytes=settings.beta_max_stored_media_bytes,
            )
        )
        db.commit()
    response = client.post(
        f"/api/v1/projects/{project_id}/youtube-imports",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": True},
    )
    assert response.status_code == 429
    assert "Storage limit reached" in response.json()["error"]["message"]


class FixtureDownloader:
    def download(self, validated, destination: Path, **kwargs):
        del kwargs
        path = destination / "source.mp4"
        path.write_bytes(b"permission-cleared-fixture")
        return DownloadedYouTubeVideo(
            path=path,
            title="Permission-cleared fixture",
            channel_name="Howlix Test",
            channel_id="fixture-channel",
            published_at="20261031",
            duration_seconds=42.5,
            extractor="Fixture",
        )


def _probe(*_args):
    return MediaProbeResult(42.5, 1920, 1080, 30.0, "h264", "aac", "mp4")


def test_worker_imports_once_then_queues_existing_validation(
    client, testing_session_factory, mock_storage, tmp_path
) -> None:
    project_id = _project(testing_session_factory)
    created = client.post(
        f"/api/v1/projects/{project_id}/youtube-imports",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": True},
    ).json()
    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        probe=_probe,
        youtube_downloader=FixtureDownloader(),
    )
    assert worker.run_once() is True
    with testing_session_factory() as db:
        value = db.get(YouTubeImport, uuid.UUID(created["id"]))
        asset = db.get(MediaAsset, uuid.UUID(created["asset_id"]))
        validation = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.asset_id == asset.id,
                ProcessingJob.job_type == ProcessingJobType.VALIDATE_MEDIA,
            )
        )
        assert value is not None and value.status == YouTubeImportStatus.COMPLETED
        assert asset is not None and asset.status == MediaAssetStatus.UPLOADED
        assert validation is not None and validation.status == ProcessingJobStatus.QUEUED
        assert mock_storage.uploaded_objects == [asset.object_key]


def test_exhausted_import_lease_recovers_to_failure_and_releases_quota(
    client, testing_session_factory, mock_storage
) -> None:
    project_id = _project(testing_session_factory)
    created = client.post(
        f"/api/v1/projects/{project_id}/youtube-imports",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "permission_confirmed": True},
    ).json()
    with testing_session_factory() as db:
        job = db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.asset_id == uuid.UUID(created["asset_id"])
            )
        )
        job.status = ProcessingJobStatus.PROCESSING
        job.attempts = job.max_attempts
        job.lease_expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.commit()
    worker = MediaValidationWorker(get_settings(), mock_storage, testing_session_factory)
    assert worker.run_once() is False
    with testing_session_factory() as db:
        value = db.get(YouTubeImport, uuid.UUID(created["id"]))
        usage = db.get(UserUsage, TEST_USER_ID)
        assert value is not None and value.status == YouTubeImportStatus.FAILED
        assert usage is not None and usage.stored_media_bytes == 0
