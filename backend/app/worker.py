from __future__ import annotations

import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    MomentAnalysisRun,
    MomentAnalysisStatus,
    MomentCandidate,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Transcript,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptWord,
    UploadSession,
    UploadSessionStatus,
    utc_now,
)
from app.services.media_probe import (
    MediaProbeError,
    MediaProbeResult,
    MediaValidationError,
    probe_media,
)
from app.services.moment_discovery import (
    MomentAnalyzer,
    PermanentMomentAnalysisError,
    SegmentData,
    TransientMomentAnalysisError,
    WordData,
    bounded_batches,
    deduplicate_ranked,
    generate_candidate_windows,
    get_moment_analyzer,
    merge_usage,
    refine_boundaries,
    score_breakdown,
)
from app.services.storage import StorageError, StorageService, get_storage_service
from app.services.audio_preprocessing import AudioPreprocessingError, extract_audio_chunks
from app.services.transcription import (
    EmptyTranscriptError,
    PermanentTranscriptionError,
    TranscriptionProvider,
    TransientTranscriptionError,
    get_transcription_provider,
    merge_chunk_results,
)


logger = logging.getLogger("howlix.worker")
ProbeFunction = Callable[[Path, str, int, int], MediaProbeResult]


def claim_next_job(
    db: Session, worker_id: str, settings: Settings, now: datetime | None = None
) -> uuid.UUID | None:
    now = now or datetime.now(timezone.utc)
    with db.begin():
        exhausted = list(
            db.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.status == ProcessingJobStatus.PROCESSING,
                    ProcessingJob.lease_expires_at < now,
                    ProcessingJob.attempts >= ProcessingJob.max_attempts,
                )
            )
        )
        for job in exhausted:
            job.status = ProcessingJobStatus.FAILED
            job.finished_at = now
            job.claimed_by = None
            job.lease_expires_at = None
            job.error_message = job.error_message or "Job lease expired after all attempts."
            if job.job_type == ProcessingJobType.TRANSCRIBE_MEDIA:
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                )
                if transcript is not None:
                    transcript.status = TranscriptStatus.FAILED
            elif job.job_type == ProcessingJobType.MOMENT_DISCOVERY:
                run = db.scalar(
                    select(MomentAnalysisRun)
                    .where(MomentAnalysisRun.asset_id == job.asset_id)
                    .order_by(MomentAnalysisRun.created_at.desc())
                    .limit(1)
                )
                if run is not None:
                    run.status = MomentAnalysisStatus.FAILED
                    run.error_message = job.error_message

        statement = (
            select(ProcessingJob)
            .where(
                ProcessingJob.attempts < ProcessingJob.max_attempts,
                or_(
                    ProcessingJob.status == ProcessingJobStatus.QUEUED,
                    (
                        (ProcessingJob.status == ProcessingJobStatus.RETRY)
                        & (
                            (ProcessingJob.lease_expires_at.is_(None))
                            | (ProcessingJob.lease_expires_at < now)
                        )
                    ),
                    (
                        (ProcessingJob.status == ProcessingJobStatus.PROCESSING)
                        & (ProcessingJob.lease_expires_at < now)
                    ),
                ),
            )
            .order_by(ProcessingJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.scalar(statement)
        if job is None:
            return None
        job.status = ProcessingJobStatus.PROCESSING
        job.attempts += 1
        job.claimed_by = worker_id
        job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
        job.started_at = job.started_at or now
        job.finished_at = None
        return job.id


class LeaseHeartbeat:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        job_id: uuid.UUID,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.stop_event = Event()
        self.thread = Thread(target=self._run, daemon=True, name="howlix-job-heartbeat")

    def __enter__(self) -> "LeaseHeartbeat":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(10, self.lease_seconds // 3)
        while not self.stop_event.wait(interval):
            with self.session_factory() as db:
                job = db.get(ProcessingJob, self.job_id)
                if (
                    job is None
                    or job.status != ProcessingJobStatus.PROCESSING
                    or job.claimed_by != self.worker_id
                ):
                    return
                job.lease_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=self.lease_seconds
                )
                db.commit()


class MediaValidationWorker:
    def __init__(
        self,
        settings: Settings,
        storage: StorageService,
        session_factory: sessionmaker[Session] = SessionLocal,
        probe: ProbeFunction = probe_media,
        transcription_provider: TranscriptionProvider | None = None,
        moment_analyzer: MomentAnalyzer | None = None,
        audio_extractor=extract_audio_chunks,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.session_factory = session_factory
        self.probe = probe
        self.transcription_provider = transcription_provider
        self.moment_analyzer = moment_analyzer
        self.audio_extractor = audio_extractor
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"

    def cleanup_expired_uploads(self) -> int:
        now = datetime.now(timezone.utc)
        cleaned = 0
        with self.session_factory() as db:
            sessions = list(
                db.scalars(
                    select(UploadSession).where(
                        UploadSession.status.in_(
                            [UploadSessionStatus.INITIATED, UploadSessionStatus.UPLOADING]
                        ),
                        UploadSession.expires_at < now,
                    )
                )
            )
            for session in sessions:
                asset = db.get(MediaAsset, session.asset_id)
                if asset is None:
                    continue
                try:
                    self.storage.abort_multipart_upload(
                        asset.object_key, session.r2_upload_id
                    )
                except StorageError as exc:
                    if exc.code not in {"NoSuchUpload", "404", "10024"}:
                        logger.warning("Could not abort expired upload %s", session.id)
                        continue
                session.status = UploadSessionStatus.EXPIRED
                asset.status = MediaAssetStatus.ABORTED
                cleaned += 1
            db.commit()
        return cleaned

    def run_once(self) -> bool:
        with self.session_factory() as db:
            job_id = claim_next_job(db, self.worker_id, self.settings)
        if job_id is None:
            return False
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            job_type = job.job_type if job else None
        if job_type == ProcessingJobType.TRANSCRIBE_MEDIA:
            self._process_transcription_job(job_id)
        elif job_type == ProcessingJobType.MOMENT_DISCOVERY:
            self._process_moment_discovery_job(job_id)
        else:
            self._process_validation_job(job_id)
        return True

    def _process_validation_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            asset = db.get(MediaAsset, job.asset_id)
            if asset is None:
                self._finish_infrastructure_failure(db, job, None, "Media asset is missing.")
                return
            asset.status = MediaAssetStatus.VALIDATING
            db.commit()
            suffix = Path(asset.original_filename).suffix.lower()

        temp_root = self.settings.processing_temp_dir
        if temp_root is not None:
            temp_root = temp_root.resolve()
            temp_root.mkdir(parents=True, exist_ok=True)
        try:
            with LeaseHeartbeat(
                self.session_factory,
                job_id,
                self.worker_id,
                self.settings.job_lease_seconds,
            ):
                with tempfile.TemporaryDirectory(
                    prefix="howlix-", dir=str(temp_root) if temp_root else None
                ) as temp_directory:
                    local_path = Path(temp_directory).resolve() / f"source{suffix}"
                    self.storage.download_object(asset.object_key, local_path)
                    if local_path.stat().st_size != asset.file_size_bytes:
                        raise MediaValidationError(
                            "The downloaded object size does not match its upload metadata."
                        )
                    metadata = self.probe(
                        local_path,
                        self.settings.ffprobe_path,
                        self.settings.ffprobe_timeout_seconds,
                        self.settings.max_video_duration_seconds,
                    )
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job is None or asset is None or job.claimed_by != self.worker_id:
                    return
                asset.duration_seconds = metadata.duration_seconds
                asset.width = metadata.width
                asset.height = metadata.height
                asset.frame_rate = metadata.frame_rate
                asset.video_codec = metadata.video_codec
                asset.audio_codec = metadata.audio_codec
                asset.container_format = metadata.container_format
                asset.status = MediaAssetStatus.READY
                self._mark_job_succeeded(job)
                db.commit()
        except MediaValidationError as exc:
            deletion_error = None
            if self.settings.delete_invalid_media:
                try:
                    self.storage.delete_object(asset.object_key)
                except StorageError:
                    deletion_error = " Invalid object cleanup failed and must be retried manually."
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job is None or asset is None:
                    return
                asset.status = MediaAssetStatus.REJECTED
                job.status = ProcessingJobStatus.SUCCEEDED
                job.error_message = f"{exc}{deletion_error or ''}"
                job.finished_at = utc_now()
                job.claimed_by = None
                job.lease_expires_at = None
                db.commit()
        except (MediaProbeError, StorageError, OSError) as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job is not None:
                    self._finish_infrastructure_failure(db, job, asset, str(exc))
        except Exception as exc:
            logger.exception("Unexpected validation worker failure for job %s", job_id)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job is not None:
                    self._finish_infrastructure_failure(
                        db, job, asset, f"Unexpected worker failure: {type(exc).__name__}"
                    )

    @staticmethod
    def _mark_job_succeeded(job: ProcessingJob) -> None:
        job.status = ProcessingJobStatus.SUCCEEDED
        job.error_message = None
        job.progress_stage = "completed"
        job.finished_at = utc_now()
        job.claimed_by = None
        job.lease_expires_at = None

    @staticmethod
    def _finish_infrastructure_failure(
        db: Session,
        job: ProcessingJob,
        asset: MediaAsset | None,
        message: str,
    ) -> None:
        job.error_message = message[:2000]
        job.claimed_by = None
        job.lease_expires_at = None
        if job.attempts < job.max_attempts:
            job.status = ProcessingJobStatus.QUEUED
            if asset is not None:
                asset.status = MediaAssetStatus.UPLOADED
        else:
            job.status = ProcessingJobStatus.FAILED
            job.finished_at = utc_now()
            if asset is not None:
                asset.status = MediaAssetStatus.FAILED
        db.commit()

    def _set_progress(
        self,
        job_id: uuid.UUID,
        stage: str,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            job.progress_stage = stage
            job.progress_completed = completed
            job.progress_total = total
            db.commit()

    def _process_transcription_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            asset = db.get(MediaAsset, job.asset_id)
            transcript = db.scalar(
                select(Transcript).where(Transcript.asset_id == job.asset_id)
            )
            if asset is None or transcript is None:
                self._finish_transcription_failure(
                    db, job, transcript, "Transcription state is missing.", retryable=False
                )
                return
            transcript.status = TranscriptStatus.PROCESSING
            job.progress_stage = "downloading"
            job.progress_completed = None
            job.progress_total = None
            db.commit()
            suffix = Path(asset.original_filename).suffix.lower()
            object_key = asset.object_key
            expected_size = asset.file_size_bytes
            duration = asset.duration_seconds
            has_audio = bool(asset.audio_codec)

        if not has_audio:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db, job, transcript, "This video has no supported audio stream.", retryable=False
                    )
            return

        temp_root = self.settings.processing_temp_dir
        if temp_root is not None:
            temp_root = temp_root.resolve()
            temp_root.mkdir(parents=True, exist_ok=True)
        try:
            with LeaseHeartbeat(
                self.session_factory,
                job_id,
                self.worker_id,
                self.settings.job_lease_seconds,
            ):
                with tempfile.TemporaryDirectory(
                    prefix="howlix-transcription-", dir=str(temp_root) if temp_root else None
                ) as temp_directory:
                    directory = Path(temp_directory).resolve()
                    source = directory / f"source{suffix}"
                    self.storage.download_object(object_key, source)
                    if source.stat().st_size != expected_size:
                        raise TransientTranscriptionError(
                            "The downloaded object size does not match its media record."
                        )
                    self._set_progress(job_id, "extracting_audio", 0, None)
                    chunks = self.audio_extractor(
                        source,
                        directory / "audio",
                        duration_seconds=float(duration or 0),
                        ffmpeg_path=self.settings.ffmpeg_path,
                        timeout_seconds=self.settings.transcription_subprocess_timeout_seconds,
                        chunk_seconds=self.settings.transcription_chunk_seconds,
                        overlap_seconds=self.settings.transcription_chunk_overlap_seconds,
                        max_chunk_bytes=self.settings.transcription_max_chunk_bytes,
                        progress=lambda completed, total: self._set_progress(
                            job_id, "extracting_audio", completed, total
                        ),
                    )
                    provider = self.transcription_provider or get_transcription_provider(
                        self.settings
                    )
                    chunk_results = []
                    for index, chunk in enumerate(chunks):
                        self._set_progress(job_id, "transcribing", index, len(chunks))
                        chunk_results.append((chunk.offset_ms, provider.transcribe(chunk.path)))
                        self._set_progress(job_id, "transcribing", index + 1, len(chunks))
                    result = merge_chunk_results(chunk_results)

            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                ) if job else None
                if job is None or transcript is None or job.claimed_by != self.worker_id:
                    return
                db.execute(
                    delete(TranscriptWord).where(TranscriptWord.transcript_id == transcript.id)
                )
                db.execute(
                    delete(TranscriptSegment).where(
                        TranscriptSegment.transcript_id == transcript.id
                    )
                )
                persisted_segments: list[TranscriptSegment] = []
                for item in result.segments:
                    segment = TranscriptSegment(
                        transcript_id=transcript.id,
                        start_ms=item.start_ms,
                        end_ms=item.end_ms,
                        text=item.text,
                    )
                    db.add(segment)
                    persisted_segments.append(segment)
                db.flush()
                for item in result.words:
                    midpoint = (item.start_ms + item.end_ms) // 2
                    segment = next(
                        (
                            candidate
                            for candidate in persisted_segments
                            if candidate.start_ms <= midpoint <= candidate.end_ms
                        ),
                        None,
                    )
                    db.add(
                        TranscriptWord(
                            transcript_id=transcript.id,
                            segment_id=segment.id if segment else None,
                            start_ms=item.start_ms,
                            end_ms=item.end_ms,
                            word=item.word,
                            confidence=item.confidence,
                        )
                    )
                transcript.language = result.language
                transcript.full_text = result.text
                transcript.status = TranscriptStatus.COMPLETED
                self._mark_job_succeeded(job)
                job.progress_completed = len(chunk_results)
                job.progress_total = len(chunk_results)
                db.commit()
        except (EmptyTranscriptError, PermanentTranscriptionError, AudioPreprocessingError) as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db, job, transcript, str(exc), retryable=False
                    )
        except (TransientTranscriptionError, StorageError, OSError) as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db, job, transcript, str(exc), retryable=True
                    )
        except Exception as exc:
            logger.exception("Unexpected transcription worker failure for job %s", job_id)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(Transcript.asset_id == job.asset_id)
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db,
                        job,
                        transcript,
                        f"Unexpected transcription failure: {type(exc).__name__}",
                        retryable=True,
                    )

    def _finish_transcription_failure(
        self,
        db: Session,
        job: ProcessingJob,
        transcript: Transcript | None,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        job.error_message = message[:2000]
        job.claimed_by = None
        if retryable and job.attempts < job.max_attempts:
            job.status = ProcessingJobStatus.RETRY
            job.progress_stage = "retry"
            job.lease_expires_at = utc_now() + timedelta(
                seconds=min(
                    300,
                    self.settings.transcription_retry_base_seconds
                    * (2 ** max(0, job.attempts - 1)),
                )
            )
            if transcript is not None:
                transcript.status = TranscriptStatus.RETRY
        else:
            job.status = ProcessingJobStatus.FAILED
            job.progress_stage = "failed"
            job.finished_at = utc_now()
            job.lease_expires_at = None
            if transcript is not None:
                transcript.status = TranscriptStatus.FAILED
        db.commit()

    def _process_moment_discovery_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            run = db.scalar(
                select(MomentAnalysisRun)
                .where(MomentAnalysisRun.asset_id == job.asset_id)
                .order_by(MomentAnalysisRun.created_at.desc())
                .limit(1)
            )
            asset = db.get(MediaAsset, job.asset_id)
            transcript = (
                db.scalar(
                    select(Transcript)
                    .where(Transcript.id == run.transcript_id)
                    .options(
                        selectinload(Transcript.segments),
                        selectinload(Transcript.words),
                    )
                )
                if run is not None
                else None
            )
            if (
                run is None
                or asset is None
                or transcript is None
                or transcript.status != TranscriptStatus.COMPLETED
                or asset.duration_seconds is None
            ):
                self._finish_moment_failure(
                    db,
                    job,
                    run,
                    "Completed transcript and source duration are required for moment discovery.",
                    retryable=False,
                )
                return
            run.status = MomentAnalysisStatus.PROCESSING
            run.error_message = None
            job.progress_stage = "generating_candidates"
            job.progress_completed = None
            job.progress_total = None
            db.commit()
            run_id = run.id
            asset_id = asset.id
            language = transcript.language
            source_duration_ms = max(1, round(asset.duration_seconds * 1000))
            segments = [
                SegmentData(item.start_ms, item.end_ms, item.text)
                for item in transcript.segments
            ]
            words = [WordData(item.start_ms, item.end_ms, item.word) for item in transcript.words]

        minimum_ms = self.settings.moment_min_duration_seconds * 1000
        maximum_ms = self.settings.moment_max_duration_seconds * 1000
        target_ms = self.settings.moment_target_duration_seconds * 1000
        try:
            with LeaseHeartbeat(
                self.session_factory,
                job_id,
                self.worker_id,
                self.settings.job_lease_seconds,
            ):
                windows = generate_candidate_windows(
                    segments,
                    source_duration_ms=source_duration_ms,
                    min_duration_ms=minimum_ms,
                    max_duration_ms=maximum_ms,
                    target_duration_ms=target_ms,
                    max_candidates=self.settings.moment_max_candidates,
                )
                batches = bounded_batches(
                    windows,
                    batch_size=self.settings.moment_batch_size,
                    max_requests=self.settings.moment_max_api_requests,
                    max_input_chars=self.settings.moment_max_input_chars,
                )
                analyzer = self.moment_analyzer or get_moment_analyzer(self.settings)
                evaluations = {}
                usage: dict[str, int] | None = None
                for index, batch in enumerate(batches):
                    self._set_progress(job_id, "evaluating_candidates", index, len(batches))
                    result = analyzer.analyze(
                        batch,
                        language=language,
                        source_duration_ms=source_duration_ms,
                    )
                    usage = merge_usage(usage, result.usage)
                    evaluations.update(
                        {evaluation.candidate_id: evaluation for evaluation in result.evaluations}
                    )
                    self._set_progress(job_id, "evaluating_candidates", index + 1, len(batches))

                scored = []
                for window in windows:
                    evaluation = evaluations.get(window.candidate_id)
                    if evaluation is None:
                        continue
                    overall, breakdown = score_breakdown(evaluation.scores)
                    scored.append((window, evaluation, overall, breakdown))
                recommendations = deduplicate_ranked(
                    scored,
                    limit=self.settings.moment_max_recommendations,
                    minimum_score=self.settings.moment_min_editorial_score,
                )
                self._set_progress(
                    job_id,
                    "refining_boundaries",
                    0,
                    len(recommendations),
                )
                refined = []
                for index, item in enumerate(recommendations):
                    window, evaluation, overall, breakdown = item
                    start_ms, end_ms = refine_boundaries(
                        window,
                        words,
                        source_duration_ms=source_duration_ms,
                        min_duration_ms=minimum_ms,
                        max_duration_ms=maximum_ms,
                    )
                    refined.append(
                        (start_ms, end_ms, window, evaluation, overall, breakdown)
                    )
                    self._set_progress(
                        job_id,
                        "refining_boundaries",
                        index + 1,
                        len(recommendations),
                    )

            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                run = db.get(MomentAnalysisRun, run_id)
                if job is None or run is None or job.claimed_by != self.worker_id:
                    return
                db.execute(
                    delete(MomentCandidate).where(MomentCandidate.analysis_run_id == run.id)
                )
                for rank, item in enumerate(refined, start=1):
                    start_ms, end_ms, _window, evaluation, overall, breakdown = item
                    db.add(
                        MomentCandidate(
                            analysis_run_id=run.id,
                            asset_id=asset_id,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            ai_start_ms=start_ms,
                            ai_end_ms=end_ms,
                            suggested_title=evaluation.suggested_title,
                            hook_text=evaluation.hook_text,
                            topic=evaluation.topic,
                            category=evaluation.category,
                            overall_score=overall,
                            score_breakdown_json=breakdown,
                            explanation=evaluation.explanation,
                            confidence_notes=evaluation.confidence_notes,
                            needs_context=evaluation.needs_context,
                            rank=rank,
                        )
                    )
                run.status = MomentAnalysisStatus.COMPLETED
                run.usage_json = usage
                run.error_message = None
                run.completed_at = utc_now()
                self._mark_job_succeeded(job)
                job.progress_completed = len(refined)
                job.progress_total = len(refined)
                db.commit()
        except PermanentMomentAnalysisError as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                run = db.get(MomentAnalysisRun, run_id)
                if job is not None:
                    self._finish_moment_failure(db, job, run, str(exc), retryable=False)
        except TransientMomentAnalysisError as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                run = db.get(MomentAnalysisRun, run_id)
                if job is not None:
                    self._finish_moment_failure(db, job, run, str(exc), retryable=True)
        except Exception as exc:
            logger.exception("Unexpected moment discovery failure for job %s", job_id)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                run = db.get(MomentAnalysisRun, run_id)
                if job is not None:
                    self._finish_moment_failure(
                        db,
                        job,
                        run,
                        f"Unexpected moment discovery failure: {type(exc).__name__}",
                        retryable=True,
                    )

    def _finish_moment_failure(
        self,
        db: Session,
        job: ProcessingJob,
        run: MomentAnalysisRun | None,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        job.error_message = message[:2000]
        job.claimed_by = None
        if retryable and job.attempts < job.max_attempts:
            job.status = ProcessingJobStatus.RETRY
            job.progress_stage = "retry"
            job.lease_expires_at = utc_now() + timedelta(
                seconds=min(
                    300,
                    self.settings.moment_retry_base_seconds
                    * (2 ** max(0, job.attempts - 1)),
                )
            )
            if run is not None:
                run.status = MomentAnalysisStatus.RETRY
                run.error_message = message[:2000]
        else:
            job.status = ProcessingJobStatus.FAILED
            job.progress_stage = "failed"
            job.finished_at = utc_now()
            job.lease_expires_at = None
            if run is not None:
                run.status = MomentAnalysisStatus.FAILED
                run.error_message = message[:2000]
                run.completed_at = utc_now()
        db.commit()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    worker = MediaValidationWorker(settings, get_storage_service())
    logger.info("Howlix media worker started as %s", worker.worker_id)
    try:
        while True:
            worker.cleanup_expired_uploads()
            if not worker.run_once():
                time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        logger.info("Howlix media worker stopped")


if __name__ == "__main__":
    main()
