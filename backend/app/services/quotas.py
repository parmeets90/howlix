from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    UserMonthlyUsage,
    UserUsage,
)


class QuotaExceededError(ValueError):
    pass


def month_start(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    return date(current.year, current.month, 1)


def _storage_usage(db: Session, owner_id: uuid.UUID, *, lock: bool = False) -> UserUsage:
    statement = select(UserUsage).where(UserUsage.owner_id == owner_id)
    if lock:
        statement = statement.with_for_update()
    usage = db.scalar(statement)
    if usage is None:
        try:
            with db.begin_nested():
                db.add(UserUsage(owner_id=owner_id, stored_media_bytes=0))
                db.flush()
        except IntegrityError:
            pass
        usage = db.scalar(select(UserUsage).where(UserUsage.owner_id == owner_id).with_for_update())
        if usage is None:
            raise RuntimeError("Could not initialize durable user storage usage.")
    return usage


def _monthly_usage(
    db: Session, owner_id: uuid.UUID, *, lock: bool = False
) -> UserMonthlyUsage:
    period = month_start()
    statement = select(UserMonthlyUsage).where(
        UserMonthlyUsage.owner_id == owner_id,
        UserMonthlyUsage.period_start == period,
    )
    if lock:
        statement = statement.with_for_update()
    usage = db.scalar(statement)
    if usage is None:
        try:
            with db.begin_nested():
                db.add(UserMonthlyUsage(owner_id=owner_id, period_start=period))
                db.flush()
        except IntegrityError:
            pass
        usage = db.scalar(
            select(UserMonthlyUsage)
            .where(
                UserMonthlyUsage.owner_id == owner_id,
                UserMonthlyUsage.period_start == period,
            )
            .with_for_update()
        )
        if usage is None:
            raise RuntimeError("Could not initialize durable monthly usage.")
    return usage


def enforce_project_quota(db: Session, owner_id: uuid.UUID, settings: Settings) -> None:
    count = db.scalar(select(func.count(Project.id)).where(Project.owner_id == owner_id)) or 0
    if count >= settings.beta_max_projects_per_user:
        raise QuotaExceededError(
            f"Project limit reached ({settings.beta_max_projects_per_user})."
        )


def reserve_storage(
    db: Session, owner_id: uuid.UUID, byte_count: int, settings: Settings
) -> None:
    usage = _storage_usage(db, owner_id, lock=True)
    if usage.stored_media_bytes + byte_count > settings.beta_max_stored_media_bytes:
        raise QuotaExceededError(
            f"Storage limit reached ({settings.beta_max_stored_media_mb} MB)."
        )
    usage.stored_media_bytes += byte_count


def release_storage(db: Session, owner_id: uuid.UUID | None, byte_count: int) -> None:
    if owner_id is None or byte_count <= 0:
        return
    usage = _storage_usage(db, owner_id, lock=True)
    usage.stored_media_bytes = max(0, usage.stored_media_bytes - byte_count)


def consume_transcription(
    db: Session, owner_id: uuid.UUID, duration_seconds: float, settings: Settings
) -> None:
    usage = _monthly_usage(db, owner_id, lock=True)
    seconds = max(1, round(duration_seconds))
    limit = settings.beta_monthly_transcription_minutes * 60
    if usage.transcription_seconds + seconds > limit:
        raise QuotaExceededError(
            f"Monthly transcription limit reached ({settings.beta_monthly_transcription_minutes} minutes)."
        )
    usage.transcription_seconds += seconds


def consume_analysis(db: Session, owner_id: uuid.UUID, settings: Settings) -> None:
    usage = _monthly_usage(db, owner_id, lock=True)
    if usage.analysis_jobs + 1 > settings.beta_monthly_analysis_jobs:
        raise QuotaExceededError(
            f"Monthly AI analysis limit reached ({settings.beta_monthly_analysis_jobs} jobs)."
        )
    usage.analysis_jobs += 1


def enforce_render_concurrency(
    db: Session, owner_id: uuid.UUID, settings: Settings
) -> None:
    active = db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.owner_id == owner_id,
            ProcessingJob.job_type == ProcessingJobType.CLIP_RENDER,
            ProcessingJob.status.in_(
                [
                    ProcessingJobStatus.QUEUED,
                    ProcessingJobStatus.PROCESSING,
                    ProcessingJobStatus.RETRY,
                ]
            ),
        )
    ) or 0
    if active >= settings.beta_max_concurrent_renders:
        raise QuotaExceededError(
            f"Concurrent render limit reached ({settings.beta_max_concurrent_renders})."
        )


def enforce_youtube_import_concurrency(
    db: Session, owner_id: uuid.UUID, settings: Settings
) -> None:
    active = db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.owner_id == owner_id,
            ProcessingJob.job_type == ProcessingJobType.YOUTUBE_IMPORT,
            ProcessingJob.status.in_(
                [
                    ProcessingJobStatus.QUEUED,
                    ProcessingJobStatus.PROCESSING,
                    ProcessingJobStatus.RETRY,
                ]
            ),
        )
    ) or 0
    if active >= settings.youtube_import_max_concurrent_per_user:
        raise QuotaExceededError(
            f"Concurrent YouTube import limit reached ({settings.youtube_import_max_concurrent_per_user})."
        )


@dataclass(frozen=True)
class UsageSnapshot:
    projects_used: int
    projects_limit: int
    stored_media_bytes: int
    stored_media_limit_bytes: int
    transcription_seconds: int
    transcription_limit_seconds: int
    analysis_jobs: int
    analysis_jobs_limit: int
    concurrent_renders: int
    concurrent_renders_limit: int
    period_start: date


def usage_snapshot(db: Session, owner_id: uuid.UUID, settings: Settings) -> UsageSnapshot:
    storage = _storage_usage(db, owner_id)
    monthly = _monthly_usage(db, owner_id)
    projects = db.scalar(select(func.count(Project.id)).where(Project.owner_id == owner_id)) or 0
    renders = db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.owner_id == owner_id,
            ProcessingJob.job_type == ProcessingJobType.CLIP_RENDER,
            ProcessingJob.status.in_(
                [
                    ProcessingJobStatus.QUEUED,
                    ProcessingJobStatus.PROCESSING,
                    ProcessingJobStatus.RETRY,
                ]
            ),
        )
    ) or 0
    return UsageSnapshot(
        projects,
        settings.beta_max_projects_per_user,
        storage.stored_media_bytes,
        settings.beta_max_stored_media_bytes,
        monthly.transcription_seconds,
        settings.beta_monthly_transcription_minutes * 60,
        monthly.analysis_jobs,
        settings.beta_monthly_analysis_jobs,
        renders,
        settings.beta_max_concurrent_renders,
        monthly.period_start,
    )
