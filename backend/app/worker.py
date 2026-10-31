from __future__ import annotations

import logging
import argparse
import sys
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
    CaptionPreset,
    ClipExport,
    ClipExportStatus,
    FramingMode,
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
    YouTubeImport,
    YouTubeImportStatus,
    utc_now,
)
from app.services.media_probe import (
    MediaProbeError,
    MediaProbeResult,
    MediaValidationError,
    probe_media,
)
from app.services.clip_extraction import (
    ClipBoundaryError,
    clip_relative_words,
    validate_clip_range,
)
from app.services.export_storage import upload_export
from app.services.export_validation import ExportValidationError, validate_export
from app.services.face_detection import detect_face_focus
from app.services.ffmpeg_commands import RenderCommandOptions
from app.services.framing import calculate_crop, output_dimensions
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
from app.services.rendering import (
    RenderCancelled,
    RenderError,
    render_with_fallback,
    select_encoder,
)
from app.services.quotas import release_storage, reserve_storage
from app.services.subtitles import CaptionStyle, build_ass_document, write_ass_file
from app.services.audio_preprocessing import AudioPreprocessingError, extract_audio_chunks
from app.services.transcription import (
    EmptyTranscriptError,
    PermanentTranscriptionError,
    TranscriptionProvider,
    TransientTranscriptionError,
    get_transcription_provider,
    merge_chunk_results,
)
from app.services.youtube_import import (
    YtDlpDownloader,
    YouTubeDownloader,
    YouTubeImportCancelled,
    YouTubeImportError,
    YouTubeImportLimitError,
    YouTubeImportUnavailable,
    ValidatedYouTubeUrl,
)
from app.services.github_dispatch import dispatch_job


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
                    ProcessingJob.owner_id.is_not(None),
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
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
                )
                if transcript is not None:
                    transcript.status = TranscriptStatus.FAILED
            elif job.job_type == ProcessingJobType.MOMENT_DISCOVERY:
                run = db.scalar(
                    select(MomentAnalysisRun)
                    .where(
                        MomentAnalysisRun.asset_id == job.asset_id,
                        MomentAnalysisRun.owner_id == job.owner_id,
                    )
                    .order_by(MomentAnalysisRun.created_at.desc())
                    .limit(1)
                )
                if run is not None:
                    run.status = MomentAnalysisStatus.FAILED
                    run.error_message = job.error_message
            elif job.job_type == ProcessingJobType.CLIP_RENDER and job.clip_export_id:
                export = db.get(ClipExport, job.clip_export_id)
                if export is not None and export.status != ClipExportStatus.CANCELLED:
                    export.status = ClipExportStatus.FAILED
                    export.error_message = job.error_message
                    export.completed_at = now
            elif job.job_type == ProcessingJobType.YOUTUBE_IMPORT:
                value = db.scalar(
                    select(YouTubeImport).where(
                        YouTubeImport.asset_id == job.asset_id,
                        YouTubeImport.owner_id == job.owner_id,
                    )
                )
                if value is not None:
                    value.status = YouTubeImportStatus.FAILED
                    value.error_message = job.error_message
                    value.completed_at = now
                    if value.reservation_active:
                        release_storage(db, value.owner_id, value.reserved_bytes)
                        value.reservation_active = False

        active_render = db.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.CLIP_RENDER,
                ProcessingJob.owner_id.is_not(None),
                ProcessingJob.status == ProcessingJobStatus.PROCESSING,
                ProcessingJob.lease_expires_at >= now,
            )
            .limit(1)
        )

        statement = (
            select(ProcessingJob)
            .where(
                ProcessingJob.attempts < ProcessingJob.max_attempts,
                ProcessingJob.owner_id.is_not(None),
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
        if active_render is not None:
            statement = statement.where(ProcessingJob.job_type != ProcessingJobType.CLIP_RENDER)
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


def claim_job_by_id(
    db: Session,
    job_id: uuid.UUID,
    worker_id: str,
    settings: Settings,
    now: datetime | None = None,
) -> uuid.UUID | None:
    """Atomically claim one explicitly authorized persisted job."""
    now = now or datetime.now(timezone.utc)
    with db.begin():
        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        if (
            job is None
            or job.owner_id is None
            or job.job_type not in set(ProcessingJobType)
            or job.attempts >= job.max_attempts
        ):
            return None
        asset = db.get(MediaAsset, job.asset_id)
        if asset is None or asset.owner_id != job.owner_id:
            return None
        eligible = job.status == ProcessingJobStatus.QUEUED or (
            job.status in {ProcessingJobStatus.RETRY, ProcessingJobStatus.PROCESSING}
            and (
                job.lease_expires_at is None
                or job.lease_expires_at.replace(
                    tzinfo=job.lease_expires_at.tzinfo or timezone.utc
                )
                < now
            )
        )
        if not eligible:
            return None
        if job.job_type == ProcessingJobType.CLIP_RENDER:
            active_render = db.scalar(
                select(ProcessingJob.id)
                .where(
                    ProcessingJob.id != job.id,
                    ProcessingJob.job_type == ProcessingJobType.CLIP_RENDER,
                    ProcessingJob.status == ProcessingJobStatus.PROCESSING,
                    ProcessingJob.lease_expires_at >= now,
                )
                .limit(1)
            )
            if active_render is not None:
                return None
        job.status = ProcessingJobStatus.PROCESSING
        job.attempts += 1
        job.claimed_by = worker_id
        job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
        job.started_at = job.started_at or now
        job.finished_at = None
        job.dispatch_error_message = None
        job.progress_stage = "processing"
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
        clip_renderer=render_with_fallback,
        face_focus_detector=detect_face_focus,
        export_validator=validate_export,
        export_uploader=upload_export,
        youtube_downloader: YouTubeDownloader | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.session_factory = session_factory
        self.probe = probe
        self.transcription_provider = transcription_provider
        self.moment_analyzer = moment_analyzer
        self.audio_extractor = audio_extractor
        self.clip_renderer = clip_renderer
        self.face_focus_detector = face_focus_detector
        self.export_validator = export_validator
        self.export_uploader = export_uploader
        self.youtube_downloader = youtube_downloader or YtDlpDownloader()
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
                        logger.warning("Could not abort an expired multipart upload.")
                        continue
                session.status = UploadSessionStatus.EXPIRED
                asset.status = MediaAssetStatus.ABORTED
                release_storage(db, asset.owner_id, asset.file_size_bytes)
                cleaned += 1
            db.commit()
        return cleaned

    def run_once(self) -> bool:
        with self.session_factory() as db:
            job_id = claim_next_job(db, self.worker_id, self.settings)
        if job_id is None:
            return False
        self._process_claimed_job(job_id)
        return True

    def run_job_by_id(self, job_id: uuid.UUID) -> bool:
        with self.session_factory() as db:
            claimed = claim_job_by_id(db, job_id, self.worker_id, self.settings)
        if claimed is None:
            return False
        self._process_claimed_job(claimed)
        return True

    def _process_claimed_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            job_type = job.job_type if job else None
        if job_type == ProcessingJobType.TRANSCRIBE_MEDIA:
            self._process_transcription_job(job_id)
        elif job_type == ProcessingJobType.MOMENT_DISCOVERY:
            self._process_moment_discovery_job(job_id)
        elif job_type == ProcessingJobType.CLIP_RENDER:
            self._process_clip_render_job(job_id)
        elif job_type == ProcessingJobType.YOUTUBE_IMPORT:
            self._process_youtube_import_job(job_id)
        else:
            self._process_validation_job(job_id)

    def _process_validation_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            asset = db.get(MediaAsset, job.asset_id)
            if asset is not None and asset.owner_id != job.owner_id:
                asset = None
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
                if deletion_error is None:
                    release_storage(db, asset.owner_id, asset.file_size_bytes)
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
            logger.error("Unexpected validation worker failure.")
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

    def _youtube_cancelled(self, import_id: uuid.UUID) -> bool:
        with self.session_factory() as db:
            value = db.get(YouTubeImport, import_id)
            if value is None or value.status == YouTubeImportStatus.CANCELLED:
                return True
            job = db.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.asset_id == value.asset_id,
                    ProcessingJob.job_type == ProcessingJobType.YOUTUBE_IMPORT,
                )
            )
            return job is None or job.status == ProcessingJobStatus.CANCELLED

    def _cleanup_import_object(self, object_key: str) -> None:
        try:
            self.storage.delete_object(object_key)
        except StorageError as exc:
            if exc.code not in {"NoSuchKey", "404", "10024"}:
                logger.warning("Could not clean an incomplete YouTube import object.")

    def _process_youtube_import_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            asset = db.get(MediaAsset, job.asset_id)
            value = db.scalar(
                select(YouTubeImport).where(
                    YouTubeImport.asset_id == job.asset_id,
                    YouTubeImport.owner_id == job.owner_id,
                )
            )
            if asset is None or value is None or asset.owner_id != job.owner_id:
                self._finish_infrastructure_failure(db, job, asset, "YouTube import state is missing.")
                return
            if value.status == YouTubeImportStatus.COMPLETED:
                self._mark_job_succeeded(job)
                db.commit()
                return
            if value.status == YouTubeImportStatus.CANCELLED:
                job.status = ProcessingJobStatus.CANCELLED
                job.claimed_by = None
                job.lease_expires_at = None
                job.finished_at = utc_now()
                db.commit()
                return
            value.status = YouTubeImportStatus.PROCESSING
            value.started_at = value.started_at or utc_now()
            value.error_message = None
            asset.status = MediaAssetStatus.IMPORTING
            job.progress_stage = "resolving_youtube"
            import_id = value.id
            object_key = asset.object_key
            validated = ValidatedYouTubeUrl(value.source_url, value.canonical_url, value.video_id)
            db.commit()

        temp_root = self.settings.processing_temp_dir
        if temp_root is not None:
            temp_root = temp_root.resolve()
            temp_root.mkdir(parents=True, exist_ok=True)
        uploaded = False
        try:
            with LeaseHeartbeat(
                self.session_factory, job_id, self.worker_id, self.settings.job_lease_seconds
            ):
                with tempfile.TemporaryDirectory(
                    prefix="howlix-youtube-", dir=str(temp_root) if temp_root else None
                ) as temp_directory:
                    self._set_progress(job_id, "downloading_youtube")
                    downloaded = self.youtube_downloader.download(
                        validated,
                        Path(temp_directory),
                        maximum_bytes=min(
                            self.settings.youtube_import_max_bytes,
                            self.settings.max_upload_size_mb * 1024 * 1024,
                        ),
                        maximum_duration_seconds=self.settings.max_video_duration_seconds,
                        timeout_seconds=self.settings.youtube_import_timeout_seconds,
                        progress=lambda completed, total: self._set_progress(
                            job_id, "downloading_youtube", completed, total
                        ),
                        cancelled=lambda: self._youtube_cancelled(import_id),
                    )
                    if self._youtube_cancelled(import_id):
                        raise YouTubeImportCancelled("YouTube import was cancelled.")
                    self._set_progress(job_id, "probing_youtube")
                    metadata = self.probe(
                        downloaded.path,
                        self.settings.ffprobe_path,
                        self.settings.ffprobe_timeout_seconds,
                        self.settings.max_video_duration_seconds,
                    )
                    actual_size = downloaded.path.stat().st_size
                    if actual_size <= 0 or actual_size > self.settings.youtube_import_max_bytes:
                        raise YouTubeImportLimitError(
                            "The downloaded video exceeds this workspace's import size limit."
                        )
                    self._set_progress(job_id, "uploading_to_private_storage", actual_size, actual_size)
                    self._cleanup_import_object(object_key)
                    self.storage.upload_object(
                        object_key,
                        downloaded.path,
                        "video/mp4",
                        {
                            "source": "youtube",
                            "youtube-video-id": validated.video_id,
                            "howlix-import-id": str(import_id),
                        },
                    )
                    uploaded = True
                    head = self.storage.head_object(object_key)
                    if head.content_length != actual_size:
                        raise StorageError("R2 import upload size verification failed.")
                    if self._youtube_cancelled(import_id):
                        raise YouTubeImportCancelled("YouTube import was cancelled.")

            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                value = db.get(YouTubeImport, import_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job is None or value is None or asset is None or job.claimed_by != self.worker_id:
                    return
                if value.status == YouTubeImportStatus.CANCELLED:
                    raise YouTubeImportCancelled("YouTube import was cancelled.")
                asset.file_size_bytes = actual_size
                asset.duration_seconds = metadata.duration_seconds
                asset.width = metadata.width
                asset.height = metadata.height
                asset.frame_rate = metadata.frame_rate
                asset.video_codec = metadata.video_codec
                asset.audio_codec = metadata.audio_codec
                asset.container_format = metadata.container_format
                asset.status = MediaAssetStatus.UPLOADED
                value.title = downloaded.title
                value.channel_name = downloaded.channel_name
                value.channel_id = downloaded.channel_id
                value.published_at = downloaded.published_at
                value.source_duration_seconds = downloaded.duration_seconds
                value.extractor = downloaded.extractor
                value.status = YouTubeImportStatus.COMPLETED
                value.error_message = None
                value.completed_at = utc_now()
                if value.reservation_active:
                    release_storage(db, value.owner_id, max(0, value.reserved_bytes - actual_size))
                    value.reservation_active = False
                validation_job = db.scalar(
                    select(ProcessingJob).where(
                        ProcessingJob.asset_id == asset.id,
                        ProcessingJob.job_type == ProcessingJobType.VALIDATE_MEDIA,
                    )
                )
                if validation_job is None:
                    validation_job = ProcessingJob(
                        owner_id=value.owner_id,
                        asset_id=asset.id,
                        job_type=ProcessingJobType.VALIDATE_MEDIA,
                        status=ProcessingJobStatus.QUEUED,
                        max_attempts=3,
                        progress_stage="queued",
                    )
                    db.add(validation_job)
                    db.flush()
                self._mark_job_succeeded(job)
                job.progress_completed = actual_size
                job.progress_total = actual_size
                db.commit()
                dispatch_job(
                    db, validation_job.id, self.settings, owner_id=value.owner_id
                )
        except YouTubeImportCancelled as exc:
            if uploaded:
                self._cleanup_import_object(object_key)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                value = db.get(YouTubeImport, import_id)
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if value is not None and value.reservation_active:
                    release_storage(db, value.owner_id, value.reserved_bytes)
                    value.reservation_active = False
                if value is not None:
                    value.status = YouTubeImportStatus.CANCELLED
                    value.error_message = str(exc)
                    value.completed_at = utc_now()
                if asset is not None:
                    asset.status = MediaAssetStatus.ABORTED
                if job is not None:
                    job.status = ProcessingJobStatus.CANCELLED
                    job.error_message = str(exc)
                    job.progress_stage = "cancelled"
                    job.claimed_by = None
                    job.lease_expires_at = None
                    job.finished_at = utc_now()
                db.commit()
        except (YouTubeImportUnavailable, YouTubeImportLimitError, MediaValidationError) as exc:
            if uploaded:
                self._cleanup_import_object(object_key)
            self._finish_youtube_import_failure(job_id, import_id, str(exc), retryable=False)
        except (StorageError, MediaProbeError, OSError, YouTubeImportError) as exc:
            if uploaded:
                self._cleanup_import_object(object_key)
            self._finish_youtube_import_failure(job_id, import_id, str(exc), retryable=True)
        except Exception as exc:
            logger.error("Unexpected YouTube import failure.")
            if uploaded:
                self._cleanup_import_object(object_key)
            self._finish_youtube_import_failure(
                job_id,
                import_id,
                f"Unexpected YouTube import failure: {type(exc).__name__}",
                retryable=True,
            )

    def _finish_youtube_import_failure(
        self, job_id: uuid.UUID, import_id: uuid.UUID, message: str, *, retryable: bool
    ) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            value = db.get(YouTubeImport, import_id)
            asset = db.get(MediaAsset, job.asset_id) if job else None
            if job is None:
                return
            job.error_message = message[:2000]
            job.claimed_by = None
            if retryable and job.attempts < job.max_attempts:
                job.status = ProcessingJobStatus.RETRY
                job.progress_stage = "retry"
                job.lease_expires_at = utc_now() + timedelta(
                    seconds=min(300, 5 * (2 ** max(0, job.attempts - 1)))
                )
                if value is not None:
                    value.status = YouTubeImportStatus.RETRY
                    value.error_message = message[:2000]
                if asset is not None:
                    asset.status = MediaAssetStatus.IMPORTING
            else:
                job.status = ProcessingJobStatus.FAILED
                job.progress_stage = "failed"
                job.lease_expires_at = None
                job.finished_at = utc_now()
                if value is not None:
                    value.status = YouTubeImportStatus.FAILED
                    value.error_message = message[:2000]
                    value.completed_at = utc_now()
                    if value.reservation_active:
                        release_storage(db, value.owner_id, value.reserved_bytes)
                        value.reservation_active = False
                if asset is not None:
                    asset.status = MediaAssetStatus.FAILED
            db.commit()

    def _process_transcription_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.claimed_by != self.worker_id:
                return
            asset = db.get(MediaAsset, job.asset_id)
            if asset is not None and asset.owner_id != job.owner_id:
                asset = None
            transcript = db.scalar(
                select(Transcript).where(
                    Transcript.asset_id == job.asset_id,
                    Transcript.owner_id == job.owner_id,
                )
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
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
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
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
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
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db, job, transcript, str(exc), retryable=False
                    )
        except (TransientTranscriptionError, StorageError, OSError) as exc:
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
                ) if job else None
                if job:
                    self._finish_transcription_failure(
                        db, job, transcript, str(exc), retryable=True
                    )
        except Exception as exc:
            logger.error("Unexpected transcription worker failure.")
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                transcript = db.scalar(
                    select(Transcript).where(
                        Transcript.asset_id == job.asset_id,
                        Transcript.owner_id == job.owner_id,
                    )
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
                .where(
                    MomentAnalysisRun.asset_id == job.asset_id,
                    MomentAnalysisRun.owner_id == job.owner_id,
                )
                .order_by(MomentAnalysisRun.created_at.desc())
                .limit(1)
            )
            asset = db.get(MediaAsset, job.asset_id)
            if asset is not None and asset.owner_id != job.owner_id:
                asset = None
            transcript = (
                db.scalar(
                    select(Transcript)
                    .where(
                        Transcript.id == run.transcript_id,
                        Transcript.owner_id == job.owner_id,
                    )
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
                            owner_id=run.owner_id,
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
            logger.error("Unexpected moment discovery failure.")
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

    def _export_cancelled(self, export_id: uuid.UUID) -> bool:
        with self.session_factory() as db:
            export = db.get(ClipExport, export_id)
            return export is None or export.status == ClipExportStatus.CANCELLED

    def _cleanup_export_object(self, object_key: str | None) -> None:
        if not object_key:
            return
        try:
            self.storage.delete_object(object_key)
        except StorageError as exc:
            if exc.code not in {"NoSuchKey", "404"}:
                logger.warning("Could not clean an incomplete export object.")

    def _process_clip_render_job(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            export = db.get(ClipExport, job.clip_export_id) if job and job.clip_export_id else None
            if export is not None and export.owner_id != job.owner_id:
                export = None
            moment = db.get(MomentCandidate, export.moment_id) if export else None
            asset = db.get(MediaAsset, export.asset_id) if export else None
            if moment is not None and moment.owner_id != job.owner_id:
                moment = None
            if asset is not None and asset.owner_id != job.owner_id:
                asset = None
            transcript = (
                db.scalar(
                    select(Transcript)
                    .where(
                        Transcript.asset_id == asset.id,
                        Transcript.owner_id == job.owner_id,
                    )
                    .options(selectinload(Transcript.words))
                )
                if asset is not None
                else None
            )
            if job is None or job.claimed_by != self.worker_id:
                return
            if export is not None and export.status == ClipExportStatus.CANCELLED:
                job.status = ProcessingJobStatus.CANCELLED
                job.claimed_by = None
                job.lease_expires_at = None
                job.finished_at = utc_now()
                db.commit()
                return
            if (
                export is None
                or moment is None
                or asset is None
                or asset.duration_seconds is None
                or asset.width is None
                or asset.height is None
            ):
                self._finish_clip_failure(
                    db, job, export, "Clip export state or source metadata is missing.", retryable=False
                )
                return
            settings_json = dict(export.render_settings_json)
            try:
                clip = validate_clip_range(
                    int(settings_json["source_start_ms"]),
                    int(settings_json["source_end_ms"]),
                    source_duration_ms=round(asset.duration_seconds * 1000),
                    maximum_duration_ms=self.settings.moment_max_duration_seconds * 1000,
                )
                output_width, output_height = (
                    int(value) for value in export.resolution.split("x", 1)
                )
            except (KeyError, TypeError, ValueError, ClipBoundaryError) as exc:
                self._finish_clip_failure(db, job, export, str(exc), retryable=False)
                return
            export.status = ClipExportStatus.PROCESSING
            export.started_at = export.started_at or utc_now()
            export.completed_at = None
            export.error_message = None
            job.progress_stage = "downloading_source"
            job.progress_completed = 0
            job.progress_total = clip.duration_ms
            db.commit()
            export_id = export.id
            object_key = export.r2_object_key
            source_key = asset.object_key
            source_size = asset.file_size_bytes
            source_suffix = Path(asset.original_filename).suffix.lower() or ".mp4"
            source_width, source_height = asset.width, asset.height
            has_audio = bool(asset.audio_codec)
            project_id = asset.project_id
            words = list(transcript.words) if transcript is not None else []
            framing_mode = export.framing_mode
            caption_preset = export.caption_preset
            fps = export.fps

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
                    prefix="howlix-render-", dir=str(temp_root) if temp_root else None
                ) as temp_directory:
                    directory = Path(temp_directory).resolve()
                    source = directory / f"source{source_suffix}"
                    output = directory / "export.mp4"
                    self.storage.download_object(source_key, source)
                    if source.stat().st_size != source_size:
                        raise RenderError("Downloaded source size does not match its media record.")
                    if self._export_cancelled(export_id):
                        raise RenderCancelled("Clip export was cancelled.")

                    self._set_progress(job_id, "determining_framing", 0, clip.duration_ms)
                    focus_x, focus_y = 0.5, 0.5
                    face_fallback = False
                    if framing_mode == FramingMode.MANUAL:
                        focus_x = float(settings_json["manual_crop_x"])
                        focus_y = float(settings_json["manual_crop_y"])
                    elif framing_mode == FramingMode.FACE:
                        detected = self.face_focus_detector(
                            source,
                            start_ms=clip.start_ms,
                            end_ms=clip.end_ms,
                            sample_frequency_hz=self.settings.face_sample_frequency_hz,
                            max_samples=self.settings.face_max_samples,
                        )
                        if detected is None:
                            face_fallback = True
                        else:
                            focus_x, focus_y = detected
                    crop = calculate_crop(
                        source_width,
                        source_height,
                        output_width,
                        output_height,
                        focus_x=focus_x,
                        focus_y=focus_y,
                    )

                    relative_words = clip_relative_words(words, clip)
                    captions_filename = None
                    if caption_preset != CaptionPreset.NONE and relative_words:
                        self._set_progress(job_id, "generating_captions", 0, clip.duration_ms)
                        caption_document = build_ass_document(
                            relative_words,
                            width=output_width,
                            height=output_height,
                            style=CaptionStyle(
                                preset=caption_preset.value,
                                font_size=int(settings_json["caption_font_size"]),
                                text_color=str(settings_json["caption_text_color"]),
                                highlight_color=str(settings_json["caption_highlight_color"]),
                                vertical_position=str(settings_json["caption_vertical_position"]),
                            ),
                            latin_font=self.settings.caption_latin_font,
                            complex_font=self.settings.caption_complex_font,
                        )
                        captions_path = directory / "captions.ass"
                        write_ass_file(captions_path, caption_document)
                        captions_filename = captions_path.name

                    encoder = select_encoder(
                        self.settings.ffmpeg_path, self.settings.render_prefer_nvenc
                    )
                    self._set_progress(job_id, "rendering", 0, clip.duration_ms)
                    actual_encoder = self.clip_renderer(
                        RenderCommandOptions(
                            ffmpeg_path=self.settings.ffmpeg_path,
                            source=source,
                            output=output,
                            clip=clip,
                            crop=crop,
                            output_width=output_width,
                            output_height=output_height,
                            fps=fps,
                            encoder=encoder,
                            cpu_threads=self.settings.render_cpu_threads,
                            has_audio=has_audio,
                            captions_filename=captions_filename,
                            fonts_dir=self.settings.caption_fonts_dir,
                        ),
                        timeout_seconds=self.settings.render_timeout_seconds,
                        progress=lambda completed, total: self._set_progress(
                            job_id, "rendering", completed, total
                        ),
                        cancelled=lambda: self._export_cancelled(export_id),
                    )
                    self._set_progress(job_id, "validating_export", clip.duration_ms, clip.duration_ms)
                    validated = self.export_validator(
                        output,
                        ffprobe_path=self.settings.ffprobe_path,
                        timeout_seconds=self.settings.ffprobe_timeout_seconds,
                        expected_duration_ms=clip.duration_ms,
                        expected_width=output_width,
                        expected_height=output_height,
                        expected_audio=has_audio,
                        maximum_size_bytes=self.settings.render_max_output_bytes,
                    )
                    if self._export_cancelled(export_id):
                        raise RenderCancelled("Clip export was cancelled.")
                    self._set_progress(job_id, "uploading_export", clip.duration_ms, clip.duration_ms)
                    if not object_key:
                        raise RenderError("The server-generated export object key is missing.")
                    self._cleanup_export_object(object_key)
                    self.export_uploader(
                        self.storage,
                        object_key=object_key,
                        source=output,
                        project_id=project_id,
                        export_id=export_id,
                    )
                    if self._export_cancelled(export_id):
                        self._cleanup_export_object(object_key)
                        raise RenderCancelled("Clip export was cancelled.")

            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                export = db.get(ClipExport, export_id)
                if job is None or export is None or job.claimed_by != self.worker_id:
                    return
                reserve_storage(
                    db,
                    export.owner_id,
                    validated.file_size_bytes,
                    self.settings,
                )
                export.status = ClipExportStatus.COMPLETED
                export.file_size_bytes = validated.file_size_bytes
                export.duration_ms = round(validated.metadata.duration_seconds * 1000)
                export.video_codec = validated.metadata.video_codec
                export.audio_codec = validated.metadata.audio_codec
                export.error_message = None
                export.completed_at = utc_now()
                export.render_settings_json = {
                    **export.render_settings_json,
                    "actual_encoder": actual_encoder,
                    "focus_x": round(focus_x, 4),
                    "focus_y": round(focus_y, 4),
                    "face_fallback": face_fallback,
                }
                self._mark_job_succeeded(job)
                job.progress_completed = export.duration_ms
                job.progress_total = export.duration_ms
                db.commit()
        except RenderCancelled as exc:
            self._cleanup_export_object(object_key)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                export = db.get(ClipExport, export_id)
                if export is not None:
                    export.status = ClipExportStatus.CANCELLED
                    export.error_message = str(exc)
                    export.completed_at = utc_now()
                if job is not None:
                    job.status = ProcessingJobStatus.CANCELLED
                    job.error_message = str(exc)
                    job.progress_stage = "cancelled"
                    job.claimed_by = None
                    job.lease_expires_at = None
                    job.finished_at = utc_now()
                db.commit()
        except (ClipBoundaryError, ExportValidationError, ValueError) as exc:
            self._cleanup_export_object(object_key)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                export = db.get(ClipExport, export_id)
                if job is not None:
                    self._finish_clip_failure(db, job, export, str(exc), retryable=False)
        except (RenderError, StorageError, OSError) as exc:
            self._cleanup_export_object(object_key)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                export = db.get(ClipExport, export_id)
                if job is not None:
                    self._finish_clip_failure(db, job, export, str(exc), retryable=True)
        except Exception as exc:
            logger.error("Unexpected clip render failure.")
            self._cleanup_export_object(object_key)
            with self.session_factory() as db:
                job = db.get(ProcessingJob, job_id)
                export = db.get(ClipExport, export_id)
                if job is not None:
                    self._finish_clip_failure(
                        db,
                        job,
                        export,
                        f"Unexpected clip render failure: {type(exc).__name__}",
                        retryable=True,
                    )

    def _finish_clip_failure(
        self,
        db: Session,
        job: ProcessingJob,
        export: ClipExport | None,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        job.error_message = message[:4000]
        job.claimed_by = None
        if retryable and job.attempts < job.max_attempts:
            job.status = ProcessingJobStatus.RETRY
            job.progress_stage = "retry"
            retry_delay = min(
                300,
                self.settings.render_retry_base_seconds
                * (2 ** max(0, job.attempts - 1)),
            )
            job.lease_expires_at = (
                None if retry_delay <= 0 else utc_now() + timedelta(seconds=retry_delay)
            )
            if export is not None:
                export.status = ClipExportStatus.RETRY
                export.error_message = message[:4000]
        else:
            job.status = ProcessingJobStatus.FAILED
            job.progress_stage = "failed"
            job.finished_at = utc_now()
            job.lease_expires_at = None
            if export is not None:
                export.status = ClipExportStatus.FAILED
                export.error_message = message[:4000]
                export.completed_at = utc_now()
        db.commit()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description="Howlix durable media worker")
    parser.add_argument("--job-id", type=uuid.UUID, help="Process only this persisted job ID")
    args = parser.parse_args()
    settings = get_settings()
    worker = MediaValidationWorker(settings, get_storage_service())
    if args.job_id is not None:
        worker.worker_id = f"gha-{uuid.uuid4().hex[:12]}"
        logger.info("Howlix one-shot worker started.")
        while True:
            if worker.run_job_by_id(args.job_id):
                with worker.session_factory() as db:
                    job = db.get(ProcessingJob, args.job_id)
                    if job is None:
                        sys.exit(2)
                    if job.status == ProcessingJobStatus.RETRY and job.attempts < job.max_attempts:
                        delay = 0.0
                        if job.lease_expires_at is not None:
                            delay = max(
                                0.0,
                                (job.lease_expires_at - datetime.now(timezone.utc)).total_seconds(),
                            )
                        time.sleep(min(delay, 300.0))
                        continue
                    if job.status == ProcessingJobStatus.SUCCEEDED:
                        return
                    if job.status == ProcessingJobStatus.CANCELLED:
                        return
                    sys.exit(1)
            logger.error("Requested job is missing, ineligible, or already claimed.")
            sys.exit(2)

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
