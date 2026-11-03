from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select

from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.models import (
    CaptionPreset,
    ClipExport,
    ClipExportStatus,
    ExportAspectRatio,
    FramingMode,
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
    UploadSession,
    UploadSessionStatus,
    UserUsage,
)
from tests.conftest import SECOND_USER_ID, TEST_USER_ID


def _asset_with_export(db, project_id: uuid.UUID) -> MediaAsset:
    asset = MediaAsset(
        owner_id=TEST_USER_ID,
        project_id=project_id,
        original_filename="source.mp4",
        object_key=f"projects/{project_id}/originals/source.mp4",
        bucket_name="test",
        mime_type="video/mp4",
        file_size_bytes=1_000,
        duration_seconds=60,
        status=MediaAssetStatus.READY,
    )
    db.add(asset)
    db.flush()
    transcript = Transcript(
        owner_id=TEST_USER_ID,
        asset_id=asset.id,
        provider="fixture",
        model="fixture",
        status=TranscriptStatus.COMPLETED,
    )
    db.add(transcript)
    db.flush()
    run = MomentAnalysisRun(
        owner_id=TEST_USER_ID,
        asset_id=asset.id,
        transcript_id=transcript.id,
        status=MomentAnalysisStatus.COMPLETED,
        provider="fixture",
        model="fixture",
        prompt_version="test",
        analysis_version="test",
        settings_json={},
    )
    db.add(run)
    db.flush()
    moment = MomentCandidate(
        owner_id=TEST_USER_ID,
        analysis_run_id=run.id,
        asset_id=asset.id,
        start_ms=0,
        end_ms=30_000,
        ai_start_ms=0,
        ai_end_ms=30_000,
        suggested_title="Moment",
        hook_text="Hook",
        topic="Topic",
        category="education",
        overall_score=80,
        score_breakdown_json={},
        explanation="Good",
        confidence_notes="High",
        rank=1,
        review_status=MomentReviewStatus.APPROVED,
    )
    db.add(moment)
    db.flush()
    db.add(
        ClipExport(
            owner_id=TEST_USER_ID,
            moment_id=moment.id,
            asset_id=asset.id,
            status=ClipExportStatus.COMPLETED,
            aspect_ratio=ExportAspectRatio.VERTICAL,
            resolution="720x1280",
            fps=30,
            caption_preset=CaptionPreset.BOLD,
            framing_mode=FramingMode.CENTER,
            render_settings_json={},
            settings_hash="d" * 64,
            r2_object_key=f"projects/{project_id}/exports/clip.mp4",
            file_size_bytes=400,
            duration_ms=30_000,
        )
    )
    db.add(UserUsage(owner_id=TEST_USER_ID, stored_media_bytes=1_400))
    db.commit()
    return asset


def test_delete_video_removes_source_export_records_and_usage(
    client, testing_session_factory, mock_storage
) -> None:
    project_id = uuid.UUID(client.post("/api/v1/projects", json={"title": "Delete"}).json()["id"])
    with testing_session_factory() as db:
        asset = _asset_with_export(db, project_id)
        asset_id = asset.id

    response = client.delete(f"/api/v1/media/{asset_id}")
    assert response.status_code == 204
    assert sorted(mock_storage.deleted) == sorted(
        [
            f"projects/{project_id}/originals/source.mp4",
            f"projects/{project_id}/exports/clip.mp4",
        ]
    )
    with testing_session_factory() as db:
        assert db.get(MediaAsset, asset_id) is None
        assert db.scalar(select(UserUsage.stored_media_bytes).where(UserUsage.owner_id == TEST_USER_ID)) == 0


def test_delete_project_aborts_upload_and_removes_all_assets(
    client, testing_session_factory, mock_storage
) -> None:
    project_id = uuid.UUID(client.post("/api/v1/projects", json={"title": "Delete all"}).json()["id"])
    with testing_session_factory() as db:
        asset = MediaAsset(
            owner_id=TEST_USER_ID,
            project_id=project_id,
            original_filename="uploading.mp4",
            object_key=f"projects/{project_id}/originals/uploading.mp4",
            bucket_name="test",
            mime_type="video/mp4",
            file_size_bytes=500,
            status=MediaAssetStatus.UPLOADING,
        )
        db.add(asset)
        db.flush()
        db.add(
            UploadSession(
                owner_id=TEST_USER_ID,
                asset_id=asset.id,
                r2_upload_id="unfinished-upload",
                status=UploadSessionStatus.UPLOADING,
                part_size_bytes=5 * 1024 * 1024,
                expected_size_bytes=500,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        db.add(UserUsage(owner_id=TEST_USER_ID, stored_media_bytes=500))
        db.commit()

    response = client.delete(f"/api/v1/projects/{project_id}")
    assert response.status_code == 204
    assert mock_storage.aborted == ["unfinished-upload"]
    assert mock_storage.deleted == [f"projects/{project_id}/originals/uploading.mp4"]
    with testing_session_factory() as db:
        assert db.get(Project, project_id) is None


def test_delete_is_owner_scoped_and_blocks_active_processing(
    client, testing_session_factory, mock_storage
) -> None:
    project_id = uuid.UUID(client.post("/api/v1/projects", json={"title": "Busy"}).json()["id"])
    with testing_session_factory() as db:
        asset = MediaAsset(
            owner_id=TEST_USER_ID,
            project_id=project_id,
            original_filename="busy.mp4",
            object_key=f"projects/{project_id}/originals/busy.mp4",
            bucket_name="test",
            mime_type="video/mp4",
            file_size_bytes=500,
            status=MediaAssetStatus.VALIDATING,
        )
        db.add(asset)
        db.flush()
        db.add(
            ProcessingJob(
                owner_id=TEST_USER_ID,
                asset_id=asset.id,
                job_type=ProcessingJobType.VALIDATE_MEDIA,
                status=ProcessingJobStatus.PROCESSING,
            )
        )
        db.commit()
        asset_id = asset.id

    assert client.delete(f"/api/v1/media/{asset_id}").status_code == 409
    assert mock_storage.deleted == []
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
        SECOND_USER_ID, "user-b@example.test", "authenticated"
    )
    assert client.delete(f"/api/v1/media/{asset_id}").status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 404

