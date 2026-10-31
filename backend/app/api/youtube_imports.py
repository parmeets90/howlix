from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.responses import job_summary
from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    YouTubeImport,
    YouTubeImportStatus,
    utc_now,
)
from app.schemas import YouTubeImportCreateRequest, YouTubeImportResponse
from app.services.quotas import (
    QuotaExceededError,
    enforce_youtube_import_concurrency,
    release_storage,
    reserve_storage,
)
from app.services.youtube_import import validate_youtube_url


router = APIRouter(tags=["youtube-imports"])


def _response(value: YouTubeImport, job: ProcessingJob | None) -> YouTubeImportResponse:
    return YouTubeImportResponse(
        id=value.id,
        project_id=value.project_id,
        asset_id=value.asset_id,
        source_url=value.source_url,
        canonical_url=value.canonical_url,
        video_id=value.video_id,
        status=value.status,
        title=value.title,
        channel_name=value.channel_name,
        source_duration_seconds=value.source_duration_seconds,
        error_message=value.error_message,
        permission_confirmed_at=value.permission_confirmed_at,
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
        job=job_summary(job),
    )


def _get_import(
    db: Session, import_id: uuid.UUID, owner_id: uuid.UUID, *, lock: bool = False
) -> YouTubeImport:
    statement = select(YouTubeImport).where(
        YouTubeImport.id == import_id, YouTubeImport.owner_id == owner_id
    )
    if lock:
        statement = statement.with_for_update()
    value = db.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="YouTube import not found")
    return value


def _job(db: Session, value: YouTubeImport) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.asset_id == value.asset_id,
            ProcessingJob.owner_id == value.owner_id,
            ProcessingJob.job_type == ProcessingJobType.YOUTUBE_IMPORT,
        )
    )


@router.post(
    "/projects/{project_id}/youtube-imports",
    response_model=YouTubeImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_youtube_import(
    project_id: uuid.UUID,
    payload: YouTubeImportCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> YouTubeImportResponse:
    if not settings.youtube_import_enabled:
        raise HTTPException(status_code=503, detail="YouTube importing is disabled. Use manual upload.")
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        validated = validate_youtube_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = db.scalar(
        select(YouTubeImport).where(
            YouTubeImport.owner_id == user.id,
            YouTubeImport.project_id == project_id,
            YouTubeImport.video_id == validated.video_id,
        )
    )
    if existing is not None:
        return _response(existing, _job(db, existing))

    reservation = min(settings.youtube_import_max_bytes, settings.max_upload_size_mb * 1024 * 1024)
    project_bytes = db.scalar(
        select(func.coalesce(func.sum(MediaAsset.file_size_bytes), 0)).where(
            MediaAsset.project_id == project_id,
            MediaAsset.owner_id == user.id,
            MediaAsset.status.not_in([MediaAssetStatus.ABORTED, MediaAssetStatus.FAILED]),
        )
    ) or 0
    if project_bytes + reservation > settings.max_project_storage_mb * 1024 * 1024:
        raise HTTPException(status_code=409, detail="This project has reached its storage quota.")
    try:
        enforce_youtube_import_concurrency(db, user.id, settings)
        reserve_storage(db, user.id, reservation, settings)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    asset_id = uuid.uuid4()
    asset = MediaAsset(
        id=asset_id,
        owner_id=user.id,
        project_id=project_id,
        original_filename=f"youtube-{validated.video_id}.mp4",
        object_key=f"projects/{project_id}/media/{asset_id}.mp4",
        bucket_name=settings.r2_bucket_name,
        mime_type="video/mp4",
        file_size_bytes=1,
        status=MediaAssetStatus.IMPORTING,
    )
    value = YouTubeImport(
        owner_id=user.id,
        project_id=project_id,
        asset_id=asset_id,
        source_url=validated.source_url,
        canonical_url=validated.canonical_url,
        video_id=validated.video_id,
        status=YouTubeImportStatus.QUEUED,
        permission_confirmed_at=datetime.now(timezone.utc),
        reserved_bytes=reservation,
        reservation_active=True,
    )
    job = ProcessingJob(
        owner_id=user.id,
        asset_id=asset_id,
        job_type=ProcessingJobType.YOUTUBE_IMPORT,
        status=ProcessingJobStatus.QUEUED,
        max_attempts=settings.youtube_import_max_retries,
        progress_stage="queued",
    )
    db.add_all([asset, value, job])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(YouTubeImport).where(
                YouTubeImport.owner_id == user.id,
                YouTubeImport.project_id == project_id,
                YouTubeImport.video_id == validated.video_id,
            )
        )
        if existing is None:
            raise
        return _response(existing, _job(db, existing))
    db.refresh(value)
    db.refresh(job)
    return _response(value, job)


@router.get("/projects/{project_id}/youtube-imports", response_model=list[YouTubeImportResponse])
def list_youtube_imports(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> list[YouTubeImportResponse]:
    if db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id)) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    values = list(
        db.scalars(
            select(YouTubeImport)
            .where(YouTubeImport.project_id == project_id, YouTubeImport.owner_id == user.id)
            .order_by(YouTubeImport.created_at.desc())
        )
    )
    return [_response(value, _job(db, value)) for value in values]


@router.get("/youtube-imports/{import_id}", response_model=YouTubeImportResponse)
def get_youtube_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> YouTubeImportResponse:
    value = _get_import(db, import_id, user.id)
    return _response(value, _job(db, value))


@router.post("/youtube-imports/{import_id}/cancel", response_model=YouTubeImportResponse)
def cancel_youtube_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> YouTubeImportResponse:
    value = _get_import(db, import_id, user.id, lock=True)
    job = _job(db, value)
    if value.status in {YouTubeImportStatus.COMPLETED, YouTubeImportStatus.CANCELLED}:
        return _response(value, job)
    value.status = YouTubeImportStatus.CANCELLED
    value.error_message = "YouTube import was cancelled."
    value.completed_at = utc_now()
    if value.reservation_active:
        release_storage(db, user.id, value.reserved_bytes)
        value.reservation_active = False
    asset = db.get(MediaAsset, value.asset_id)
    if asset is not None:
        asset.status = MediaAssetStatus.ABORTED
    if job is not None:
        job.status = ProcessingJobStatus.CANCELLED
        job.error_message = value.error_message
        job.progress_stage = "cancelled"
        job.claimed_by = None
        job.lease_expires_at = None
        job.finished_at = utc_now()
    db.commit()
    return _response(value, job)


@router.post("/youtube-imports/{import_id}/retry", response_model=YouTubeImportResponse)
def retry_youtube_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> YouTubeImportResponse:
    value = _get_import(db, import_id, user.id, lock=True)
    job = _job(db, value)
    if job is None:
        raise HTTPException(status_code=409, detail="Import job is missing.")
    if value.status not in {YouTubeImportStatus.FAILED, YouTubeImportStatus.CANCELLED}:
        return _response(value, job)
    try:
        enforce_youtube_import_concurrency(db, user.id, settings)
        if not value.reservation_active:
            reserve_storage(db, user.id, value.reserved_bytes, settings)
            value.reservation_active = True
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    value.status = YouTubeImportStatus.QUEUED
    value.error_message = None
    value.completed_at = None
    asset = db.get(MediaAsset, value.asset_id)
    if asset is not None:
        asset.status = MediaAssetStatus.IMPORTING
    job.status = ProcessingJobStatus.QUEUED
    job.attempts = 0
    job.error_message = None
    job.progress_stage = "queued"
    job.progress_completed = None
    job.progress_total = None
    job.claimed_by = None
    job.lease_expires_at = None
    job.finished_at = None
    db.commit()
    return _response(value, job)
