from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import (
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
    TranscriptSegment,
    TranscriptStatus,
    TranscriptWord,
)
from app.services.moment_discovery import DeterministicFixtureAnalyzer
from app.worker import MediaValidationWorker, claim_next_job


def create_transcribed_asset(session_factory) -> uuid.UUID:
    project_id, asset_id, transcript_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with session_factory() as db:
        db.add(Project(id=project_id, title="Moment discovery test"))
        db.add(
            MediaAsset(
                id=asset_id,
                project_id=project_id,
                original_filename="interview.mp4",
                object_key=f"projects/{project_id}/originals/{asset_id}.mp4",
                bucket_name="test",
                mime_type="video/mp4",
                file_size_bytes=1024,
                duration_seconds=130,
                width=1280,
                height=720,
                frame_rate=30,
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
                language="hi",
                status=TranscriptStatus.COMPLETED,
                full_text="A complete multilingual transcript",
            )
        )
        for index in range(13):
            start_ms = index * 10_000
            end_ms = start_ms + 9_500
            segment = TranscriptSegment(
                transcript_id=transcript_id,
                start_ms=start_ms,
                end_ms=end_ms,
                text=f"कैसे सीखें useful lesson number {index}? This has a clear takeaway.",
            )
            db.add(segment)
            db.flush()
            db.add(
                TranscriptWord(
                    transcript_id=transcript_id,
                    segment_id=segment.id,
                    start_ms=start_ms + 100,
                    end_ms=end_ms - 100,
                    word=f"lesson-{index}",
                    confidence=0.95,
                )
            )
        db.commit()
    return asset_id


def _fixture_settings():
    return get_settings().model_copy(
        update={
            "moment_analysis_provider": "fixture",
            "moment_min_editorial_score": 0,
            "moment_max_candidates": 8,
            "moment_max_recommendations": 5,
        }
    )


def test_moment_request_worker_review_and_manual_edit(
    client, testing_session_factory, mock_storage
) -> None:
    asset_id = create_transcribed_asset(testing_session_factory)
    settings = _fixture_settings()
    app.dependency_overrides[get_settings] = lambda: settings

    first = client.post(f"/api/v1/media/{asset_id}/discover-moments")
    second = client.post(f"/api/v1/media/{asset_id}/discover-moments")
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]

    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        moment_analyzer=DeterministicFixtureAnalyzer(),
    )
    assert worker.run_once() is True

    analysis = client.get(f"/api/v1/media/{asset_id}/moment-analysis")
    moments = client.get(f"/api/v1/media/{asset_id}/moments")
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "completed"
    assert 1 <= analysis.json()["recommendation_count"] <= 5
    assert moments.status_code == 200
    candidate = moments.json()[0]
    assert candidate["score_breakdown"]["visual_quality"]["score"] is None
    assert candidate["transcript_excerpt"]

    new_start = candidate["start_ms"] + 100
    new_end = candidate["end_ms"] - 100
    original_score = candidate["overall_score"]
    edited = client.patch(
        f"/api/v1/moments/{candidate['id']}",
        json={"suggested_title": "Human reviewed title", "start_ms": new_start, "end_ms": new_end},
    )
    assert edited.status_code == 200
    assert edited.json()["suggested_title"] == "Human reviewed title"
    assert edited.json()["overall_score"] == original_score

    reviewed = client.post(
        f"/api/v1/moments/{candidate['id']}/review",
        json={"review_status": "approved"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "approved"
    approved = client.get(f"/api/v1/media/{asset_id}/moments?review_status=approved")
    assert [item["id"] for item in approved.json()] == [candidate["id"]]

    reset = client.patch(
        f"/api/v1/moments/{candidate['id']}", json={"reset_boundaries": True}
    )
    assert reset.status_code == 200
    assert reset.json()["start_ms"] == candidate["ai_start_ms"]
    assert reset.json()["end_ms"] == candidate["ai_end_ms"]


def test_invalid_manual_boundaries_are_rejected(
    client, testing_session_factory, mock_storage
) -> None:
    asset_id = create_transcribed_asset(testing_session_factory)
    settings = _fixture_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    client.post(f"/api/v1/media/{asset_id}/discover-moments")
    MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        moment_analyzer=DeterministicFixtureAnalyzer(),
    ).run_once()
    candidate = client.get(f"/api/v1/media/{asset_id}/moments").json()[0]
    response = client.patch(
        f"/api/v1/moments/{candidate['id']}",
        json={"start_ms": 0, "end_ms": 5_000},
    )
    assert response.status_code == 422


def test_moment_worker_retry_replaces_candidates_without_duplicates(
    client, testing_session_factory, mock_storage
) -> None:
    from app.services.moment_discovery import TransientMomentAnalysisError

    asset_id = create_transcribed_asset(testing_session_factory)
    settings = _fixture_settings().model_copy(update={"moment_retry_base_seconds": 0})
    app.dependency_overrides[get_settings] = lambda: settings
    client.post(f"/api/v1/media/{asset_id}/discover-moments")

    class FlakyAnalyzer(DeterministicFixtureAnalyzer):
        calls = 0

        def analyze(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TransientMomentAnalysisError("rate limited")
            return super().analyze(*args, **kwargs)

    analyzer = FlakyAnalyzer()
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        moment_analyzer=analyzer,
    )
    assert worker.run_once() is True
    assert worker.run_once() is True
    with testing_session_factory() as db:
        runs = list(db.scalars(select(MomentAnalysisRun)))
        candidates = list(db.scalars(select(MomentCandidate)))
        assert len(runs) == 1
        assert runs[0].status == MomentAnalysisStatus.COMPLETED
        assert len(candidates) == len({item.rank for item in candidates})


def test_interrupted_moment_job_is_reclaimed(testing_session_factory) -> None:
    asset_id = create_transcribed_asset(testing_session_factory)
    with testing_session_factory() as db:
        transcript = db.scalar(select(Transcript).where(Transcript.asset_id == asset_id))
        run = MomentAnalysisRun(
            asset_id=asset_id,
            transcript_id=transcript.id,
            status=MomentAnalysisStatus.PROCESSING,
            provider="fixture",
            model="deterministic-v1",
            prompt_version="m4-v1",
            analysis_version="1.0",
            settings_json={},
        )
        job = ProcessingJob(
            asset_id=asset_id,
            job_type=ProcessingJobType.MOMENT_DISCOVERY,
            status=ProcessingJobStatus.PROCESSING,
            attempts=1,
            claimed_by="crashed",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add_all([run, job])
        db.commit()
        job_id = job.id

    with testing_session_factory() as db:
        claimed = claim_next_job(db, "replacement", _fixture_settings())
    assert claimed == job_id
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.status == ProcessingJobStatus.PROCESSING
        assert job.attempts == 2
        assert job.claimed_by == "replacement"
