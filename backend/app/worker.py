from __future__ import annotations

import logging
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
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
from app.services.storage import StorageError, StorageService, get_storage_service


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

        statement = (
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == ProcessingJobType.VALIDATE_MEDIA,
                ProcessingJob.attempts < ProcessingJob.max_attempts,
                or_(
                    ProcessingJob.status == ProcessingJobStatus.QUEUED,
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
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.session_factory = session_factory
        self.probe = probe
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
        self._process_job(job_id)
        return True

    def _process_job(self, job_id: uuid.UUID) -> None:
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
