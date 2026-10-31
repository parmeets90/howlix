from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import (
    ClipExport,
    ClipExportStatus,
    MediaAsset,
    MediaAssetStatus,
    MomentAnalysisRun,
    MomentAnalysisStatus,
    MomentCandidate,
    MomentReviewStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    Transcript,
    TranscriptStatus,
    TranscriptWord,
)
from app.services.export_validation import ValidatedExport
from app.services.media_probe import MediaProbeResult
from app.services.rendering import RenderError
from app.worker import MediaValidationWorker, claim_next_job


def create_moment(session_factory, storage, *, approved: bool = True) -> uuid.UUID:
    project_id, asset_id, transcript_id, run_id, moment_id = [uuid.uuid4() for _ in range(5)]
    payload = b"synthetic-source"
    object_key = f"projects/{project_id}/originals/{asset_id}.mp4"
    storage.download_payloads[object_key] = payload
    storage.object_sizes[object_key] = len(payload)
    with session_factory() as db:
        db.add(Project(id=project_id, title="Export test"))
        db.add(
            MediaAsset(
                id=asset_id,
                project_id=project_id,
                original_filename="source.mp4",
                object_key=object_key,
                bucket_name=storage.bucket_name,
                mime_type="video/mp4",
                file_size_bytes=len(payload),
                duration_seconds=60,
                width=640,
                height=360,
                frame_rate=29.97,
                video_codec="h264",
                audio_codec="aac",
                container_format="mp4",
                status=MediaAssetStatus.READY,
            )
        )
        db.add(
            Transcript(
                id=transcript_id,
                asset_id=asset_id,
                provider="fixture",
                model="fixture",
                language="en",
                status=TranscriptStatus.COMPLETED,
                full_text="A useful approved moment",
            )
        )
        db.add_all(
            [
                TranscriptWord(
                    transcript_id=transcript_id,
                    start_ms=10_000 + index * 1000,
                    end_ms=10_700 + index * 1000,
                    word=word,
                    confidence=0.99,
                )
                for index, word in enumerate(["A", "useful", "approved", "moment"])
            ]
        )
        db.add(
            MomentAnalysisRun(
                id=run_id,
                asset_id=asset_id,
                transcript_id=transcript_id,
                status=MomentAnalysisStatus.COMPLETED,
                provider="fixture",
                model="fixture",
                prompt_version="m4-v1",
                analysis_version="1.0",
                settings_json={},
            )
        )
        db.add(
            MomentCandidate(
                id=moment_id,
                analysis_run_id=run_id,
                asset_id=asset_id,
                start_ms=10_000,
                end_ms=40_000,
                ai_start_ms=10_000,
                ai_end_ms=40_000,
                suggested_title="Approved moment",
                hook_text="A useful hook",
                topic="Testing",
                category="education",
                overall_score=80,
                score_breakdown_json={},
                explanation="Complete thought",
                confidence_notes="Synthetic fixture",
                needs_context=False,
                rank=1,
                review_status=(MomentReviewStatus.APPROVED if approved else MomentReviewStatus.PENDING),
            )
        )
        db.commit()
    return moment_id


def render_settings(tmp_path: Path):
    return get_settings().model_copy(
        update={
            "processing_temp_dir": tmp_path,
            "render_prefer_nvenc": False,
            "render_retry_base_seconds": 0,
        }
    )


def fake_renderer(options, *, progress, cancelled, **_kwargs):
    assert not cancelled()
    options.output.write_bytes(b"rendered-mp4")
    progress(options.clip.duration_ms, options.clip.duration_ms)
    return "libx264"


def fake_validator(path, **kwargs):
    assert path.read_bytes() == b"rendered-mp4"
    return ValidatedExport(
        MediaProbeResult(
            duration_seconds=kwargs["expected_duration_ms"] / 1000,
            width=kwargs["expected_width"],
            height=kwargs["expected_height"],
            frame_rate=30,
            video_codec="h264",
            audio_codec="aac" if kwargs["expected_audio"] else None,
            container_format="mov,mp4",
        ),
        path.stat().st_size,
    )


def test_only_approved_moments_are_exportable(client, testing_session_factory, mock_storage) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage, approved=False)
    response = client.post(f"/api/v1/moments/{moment_id}/exports", json={})
    assert response.status_code == 409


def test_export_request_is_idempotent_and_private(client, testing_session_factory, mock_storage) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    first = client.post(f"/api/v1/moments/{moment_id}/exports", json={})
    second = client.post(f"/api/v1/moments/{moment_id}/exports", json={})
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert "r2_object_key" not in first.json()
    with testing_session_factory() as db:
        assert len(list(db.scalars(select(ClipExport)))) == 1
        jobs = list(db.scalars(select(ProcessingJob)))
        assert len(jobs) == 1
        assert jobs[0].job_type == ProcessingJobType.CLIP_RENDER


def test_worker_persists_upload_and_private_download(
    client, testing_session_factory, mock_storage, tmp_path
) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    settings = render_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    queued = client.post(f"/api/v1/moments/{moment_id}/exports", json={}).json()
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        clip_renderer=fake_renderer,
        export_validator=fake_validator,
    )
    assert worker.run_once() is True
    response = client.get(f"/api/v1/exports/{queued['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["video_codec"] == "h264"
    assert response.json()["audio_codec"] == "aac"
    assert response.json()["job"]["progress_completed"] == response.json()["duration_ms"]
    assert mock_storage.uploaded_objects
    download = client.get(f"/api/v1/exports/{queued['id']}/download")
    assert download.status_code == 200
    assert "preview=1" in download.json()["download_url"]


def test_cancelled_export_is_not_rendered(client, testing_session_factory, mock_storage) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    queued = client.post(f"/api/v1/moments/{moment_id}/exports", json={}).json()
    cancelled = client.post(f"/api/v1/exports/{queued['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    with testing_session_factory() as db:
        export = db.get(ClipExport, uuid.UUID(queued["id"]))
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.clip_export_id == export.id))
        assert export.status == ClipExportStatus.CANCELLED
        assert job.status == ProcessingJobStatus.CANCELLED


def test_render_retry_does_not_duplicate_export(
    client, testing_session_factory, mock_storage, tmp_path
) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    settings = render_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    queued = client.post(f"/api/v1/moments/{moment_id}/exports", json={}).json()

    class FlakyRenderer:
        calls = 0

        def __call__(self, options, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RenderError("temporary encoder failure")
            return fake_renderer(options, **kwargs)

    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        clip_renderer=FlakyRenderer(),
        export_validator=fake_validator,
    )
    assert worker.run_once() is True
    assert worker.run_once() is True
    with testing_session_factory() as db:
        exports = list(db.scalars(select(ClipExport)))
        assert len(exports) == 1
        assert str(exports[0].id) == queued["id"]
        assert exports[0].status == ClipExportStatus.COMPLETED
    assert len(mock_storage.uploaded_objects) == 1


def test_r2_upload_failure_reaches_clear_failed_state(
    client, testing_session_factory, mock_storage, tmp_path
) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    settings = render_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    queued = client.post(f"/api/v1/moments/{moment_id}/exports", json={}).json()
    mock_storage.fail_on.add("upload-object")
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        clip_renderer=fake_renderer,
        export_validator=fake_validator,
    )
    worker.run_once()
    worker.run_once()
    response = client.get(f"/api/v1/exports/{queued['id']}").json()
    assert response["status"] == "failed"
    assert "upload" in response["error_message"].casefold()


def test_interrupted_render_job_is_reclaimed(testing_session_factory, mock_storage) -> None:
    moment_id = create_moment(testing_session_factory, mock_storage)
    with testing_session_factory() as db:
        moment = db.get(MomentCandidate, moment_id)
        export = ClipExport(
            moment_id=moment.id,
            asset_id=moment.asset_id,
            status=ClipExportStatus.PROCESSING,
            aspect_ratio="9:16",
            resolution="720x1280",
            fps=30,
            caption_preset="bold",
            framing_mode="center",
            render_settings_json={},
            settings_hash="crash-test",
            duration_ms=30_000,
        )
        db.add(export)
        db.flush()
        job = ProcessingJob(
            asset_id=moment.asset_id,
            clip_export_id=export.id,
            job_type=ProcessingJobType.CLIP_RENDER,
            status=ProcessingJobStatus.PROCESSING,
            attempts=1,
            max_attempts=2,
            claimed_by="crashed",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(job)
        db.commit()
        job_id = job.id
    with testing_session_factory() as db:
        claimed = claim_next_job(db, "replacement", get_settings())
    assert claimed == job_id
