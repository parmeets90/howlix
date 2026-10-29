from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    Transcript,
    TranscriptStatus,
)
from app.services.audio_preprocessing import AudioChunk
from app.services.transcription import (
    EmptyTranscriptError,
    TranscriptSegmentData,
    TranscriptWordData,
    TranscriptionResult,
    TransientTranscriptionError,
)
from app.worker import MediaValidationWorker, claim_next_job
from tests.conftest import MockStorageService


def create_ready_asset(session_factory, storage: MockStorageService, *, audio_codec="aac"):
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    object_key = f"projects/{project_id}/originals/{asset_id}.mp4"
    payload = b"mock-ready-video"
    storage.download_payloads[object_key] = payload
    with session_factory() as db:
        db.add(Project(id=project_id, title="Transcript test"))
        db.add(
            MediaAsset(
                id=asset_id,
                project_id=project_id,
                original_filename="interview.mp4",
                object_key=object_key,
                bucket_name=storage.bucket_name,
                mime_type="video/mp4",
                file_size_bytes=len(payload),
                duration_seconds=20,
                width=1280,
                height=720,
                frame_rate=30,
                video_codec="h264",
                audio_codec=audio_codec,
                container_format="mov,mp4",
                status=MediaAssetStatus.READY,
            )
        )
        db.commit()
    return asset_id


def test_transcription_request_is_idempotent(client, testing_session_factory, mock_storage) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage)
    settings = get_settings().model_copy(update={"groq_api_key": SecretStr("test")})
    app.dependency_overrides[get_settings] = lambda: settings
    first = client.post(f"/api/v1/media/{asset_id}/transcribe")
    second = client.post(f"/api/v1/media/{asset_id}/transcribe")
    assert first.status_code == second.status_code == 202
    assert first.json()["transcript_id"] == second.json()["transcript_id"]
    with testing_session_factory() as db:
        assert len(list(db.scalars(select(Transcript)))) == 1
        jobs = list(db.scalars(select(ProcessingJob)))
        assert len(jobs) == 1
        assert jobs[0].job_type == ProcessingJobType.TRANSCRIBE_MEDIA


def test_video_without_audio_is_rejected(client, testing_session_factory, mock_storage) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage, audio_codec=None)
    response = client.post(f"/api/v1/media/{asset_id}/transcribe")
    assert response.status_code == 409


class _Provider:
    name = "test"
    model = "test-model"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def transcribe(self, _path: Path):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _extractor(source: Path, output: Path, *, progress, **_kwargs):
    assert source.exists()
    output.mkdir(parents=True, exist_ok=True)
    audio = output / "audio.flac"
    audio.write_bytes(b"speech")
    progress(1, 1)
    return [AudioChunk(audio, 0, 20_000)]


def _result() -> TranscriptionResult:
    return TranscriptionResult(
        text="Find the moments worth watching.",
        language="en",
        segments=(TranscriptSegmentData(0, 2000, "Find the moments worth watching."),),
        words=(
            TranscriptWordData(0, 300, "Find", 0.98),
            TranscriptWordData(400, 700, "the", 0.96),
            TranscriptWordData(800, 1200, "moments", 0.97),
        ),
    )


def _queue_transcription(session_factory, asset_id):
    with session_factory() as db:
        transcript = Transcript(
            asset_id=asset_id,
            provider="test",
            model="test-model",
            status=TranscriptStatus.QUEUED,
        )
        job = ProcessingJob(
            asset_id=asset_id,
            job_type=ProcessingJobType.TRANSCRIBE_MEDIA,
            status=ProcessingJobStatus.QUEUED,
        )
        db.add_all([transcript, job])
        db.commit()
        return transcript.id, job.id


def test_worker_persists_transcript_and_cleans_temporary_files(
    client, testing_session_factory, mock_storage, tmp_path
) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage)
    transcript_id, job_id = _queue_transcription(testing_session_factory, asset_id)
    observed: list[Path] = []

    class Provider(_Provider):
        def transcribe(self, path: Path):
            observed.append(path)
            assert path.exists()
            return super().transcribe(path)

    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        transcription_provider=Provider([_result()]),
        audio_extractor=_extractor,
    )
    assert worker.run_once() is True
    assert observed and not observed[0].exists()
    with testing_session_factory() as db:
        transcript = db.get(Transcript, transcript_id)
        job = db.get(ProcessingJob, job_id)
        assert transcript is not None and job is not None
        assert transcript.status == TranscriptStatus.COMPLETED
        assert transcript.language == "en"
        assert len(transcript.segments) == 1
        assert len(transcript.words) == 3
        assert job.status == ProcessingJobStatus.SUCCEEDED
        assert (job.progress_completed, job.progress_total) == (1, 1)
    transcript_response = client.get(f"/api/v1/media/{asset_id}/transcript")
    status_response = client.get(f"/api/v1/media/{asset_id}/transcription-status")
    assert transcript_response.status_code == 200
    assert transcript_response.json()["segments"][0]["start_ms"] == 0
    assert len(transcript_response.json()["words"]) == 3
    assert status_response.json()["transcript_status"] == "completed"


def test_transient_provider_failure_retries_without_duplicate_transcript(
    testing_session_factory, mock_storage, tmp_path
) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage)
    transcript_id, job_id = _queue_transcription(testing_session_factory, asset_id)
    provider = _Provider([TransientTranscriptionError("rate limited"), _result()])
    settings = get_settings().model_copy(
        update={
            "processing_temp_dir": tmp_path,
            "transcription_retry_base_seconds": 0,
        }
    )
    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        transcription_provider=provider,
        audio_extractor=_extractor,
    )
    worker.run_once()
    with testing_session_factory() as db:
        assert db.get(ProcessingJob, job_id).status == ProcessingJobStatus.RETRY
        assert db.get(Transcript, transcript_id).status == TranscriptStatus.RETRY
    worker.run_once()
    with testing_session_factory() as db:
        assert db.get(ProcessingJob, job_id).status == ProcessingJobStatus.SUCCEEDED
        assert db.get(Transcript, transcript_id).status == TranscriptStatus.COMPLETED
        assert len(list(db.scalars(select(Transcript)))) == 1


def test_empty_speech_result_fails_without_retry(
    testing_session_factory, mock_storage, tmp_path
) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage)
    transcript_id, job_id = _queue_transcription(testing_session_factory, asset_id)
    worker = MediaValidationWorker(
        get_settings().model_copy(update={"processing_temp_dir": tmp_path}),
        mock_storage,
        testing_session_factory,
        transcription_provider=_Provider([EmptyTranscriptError("No speech was detected.")]),
        audio_extractor=_extractor,
    )
    worker.run_once()
    with testing_session_factory() as db:
        assert db.get(ProcessingJob, job_id).status == ProcessingJobStatus.FAILED
        assert db.get(Transcript, transcript_id).status == TranscriptStatus.FAILED


def test_interrupted_transcription_job_is_reclaimed(
    testing_session_factory, mock_storage
) -> None:
    asset_id = create_ready_asset(testing_session_factory, mock_storage)
    _transcript_id, job_id = _queue_transcription(testing_session_factory, asset_id)
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        job.status = ProcessingJobStatus.PROCESSING
        job.attempts = 1
        job.claimed_by = "crashed-worker"
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    with testing_session_factory() as db:
        claimed = claim_next_job(db, "replacement-worker", get_settings())

    assert claimed == job_id
    with testing_session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        assert job.status == ProcessingJobStatus.PROCESSING
        assert job.attempts == 2
        assert job.claimed_by == "replacement-worker"
