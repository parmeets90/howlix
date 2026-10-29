from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
)
from app.services.media_probe import (
    MediaProbeError,
    MediaProbeResult,
    MediaValidationError,
    parse_ffprobe_payload,
    probe_media,
)
from app.worker import MediaValidationWorker, claim_next_job
from tests.conftest import MockStorageService


def create_validation_job(
    session_factory,
    storage: MockStorageService,
    *,
    status: ProcessingJobStatus = ProcessingJobStatus.QUEUED,
    attempts: int = 0,
    max_attempts: int = 3,
    lease_expires_at=None,
    claimed_by: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    object_key = f"projects/{project_id}/originals/{asset_id}.mp4"
    payload = b"mock-video"
    storage.download_payloads[object_key] = payload
    with session_factory() as db:
        db.add(Project(id=project_id, title="Worker test"))
        db.add(
            MediaAsset(
                id=asset_id,
                project_id=project_id,
                original_filename="worker.mp4",
                object_key=object_key,
                bucket_name=storage.bucket_name,
                mime_type="video/mp4",
                file_size_bytes=len(payload),
                status=MediaAssetStatus.UPLOADED,
            )
        )
        job = ProcessingJob(
            asset_id=asset_id,
            job_type=ProcessingJobType.VALIDATE_MEDIA,
            status=status,
            attempts=attempts,
            max_attempts=max_attempts,
            lease_expires_at=lease_expires_at,
            claimed_by=claimed_by,
        )
        db.add(job)
        db.commit()
        return job.id, asset_id, object_key


def valid_probe(_path: Path, _binary: str, _timeout: int, _max_duration: int):
    return MediaProbeResult(
        duration_seconds=42.5,
        width=1920,
        height=1080,
        frame_rate=30.0,
        video_codec="h264",
        audio_codec="aac",
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
    )


def test_worker_persists_video_metadata(
    testing_session_factory, mock_storage: MockStorageService, tmp_path
) -> None:
    _job_id, asset_id, _key = create_validation_job(
        testing_session_factory, mock_storage
    )
    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    worker = MediaValidationWorker(
        settings, mock_storage, testing_session_factory, probe=valid_probe
    )
    assert worker.run_once() is True
    with testing_session_factory() as db:
        asset = db.get(MediaAsset, asset_id)
        assert asset is not None
        assert asset.status == MediaAssetStatus.READY
        assert asset.duration_seconds == 42.5
        assert (asset.width, asset.height) == (1920, 1080)
        assert asset.video_codec == "h264"


def test_corrupted_video_is_rejected_and_deleted(
    testing_session_factory, mock_storage: MockStorageService, tmp_path
) -> None:
    job_id, asset_id, object_key = create_validation_job(
        testing_session_factory, mock_storage
    )

    def corrupted(*_args):
        raise MediaValidationError("The uploaded file is corrupted.")

    settings = get_settings().model_copy(
        update={"processing_temp_dir": tmp_path, "delete_invalid_media": True}
    )
    worker = MediaValidationWorker(
        settings, mock_storage, testing_session_factory, probe=corrupted
    )
    worker.run_once()
    with testing_session_factory() as db:
        asset = db.get(MediaAsset, asset_id)
        job = db.get(ProcessingJob, job_id)
        assert asset is not None and job is not None
        assert asset.status == MediaAssetStatus.REJECTED
        assert job.status == ProcessingJobStatus.SUCCEEDED
        assert "corrupted" in (job.error_message or "")
    assert mock_storage.deleted == [object_key]


def test_video_over_duration_limit_is_rejected() -> None:
    payload = {
        "format": {"format_name": "mov,mp4", "duration": "1800.01"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30/1",
            }
        ],
    }
    with pytest.raises(MediaValidationError, match="duration limit"):
        parse_ffprobe_payload(payload, 1800)


def test_nonzero_ffprobe_exit_is_corrupted_video(monkeypatch, tmp_path) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "invalid data"

    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: Result())
    with pytest.raises(MediaValidationError, match="corrupted"):
        probe_media(tmp_path / "bad.mp4", "ffprobe", 10, 1800)


def test_expired_worker_lease_is_recovered(
    testing_session_factory, mock_storage: MockStorageService
) -> None:
    job_id, _asset_id, _key = create_validation_job(
        testing_session_factory,
        mock_storage,
        status=ProcessingJobStatus.PROCESSING,
        attempts=1,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        claimed_by="crashed-worker",
    )
    settings = get_settings()
    with testing_session_factory() as db:
        claimed = claim_next_job(db, "replacement-worker", settings)
    assert claimed == job_id
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        assert job.status == ProcessingJobStatus.PROCESSING
        assert job.claimed_by == "replacement-worker"
        assert job.attempts == 2


def test_worker_failure_cleans_temporary_file_and_requeues(
    testing_session_factory, mock_storage: MockStorageService, tmp_path
) -> None:
    job_id, asset_id, _key = create_validation_job(
        testing_session_factory, mock_storage
    )
    observed_paths: list[Path] = []

    def crash(path: Path, *_args):
        observed_paths.append(path)
        assert path.exists()
        raise MediaProbeError("FFprobe temporarily unavailable")

    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    worker = MediaValidationWorker(
        settings, mock_storage, testing_session_factory, probe=crash
    )
    worker.run_once()
    assert observed_paths and not observed_paths[0].exists()
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        asset = db.get(MediaAsset, asset_id)
        assert job is not None and asset is not None
        assert job.status == ProcessingJobStatus.QUEUED
        assert asset.status == MediaAssetStatus.UPLOADED


def test_r2_download_failure_is_retried(
    testing_session_factory, mock_storage: MockStorageService, tmp_path
) -> None:
    job_id, _asset_id, _key = create_validation_job(
        testing_session_factory, mock_storage
    )
    mock_storage.fail_on.add("download")
    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    worker = MediaValidationWorker(settings, mock_storage, testing_session_factory)
    worker.run_once()
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        assert job.status == ProcessingJobStatus.QUEUED
        assert job.attempts == 1
