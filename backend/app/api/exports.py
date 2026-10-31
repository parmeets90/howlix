from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import job_summary
from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    ClipExport,
    ClipExportStatus,
    MomentCandidate,
    MomentReviewStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
)
from app.schemas import (
    ClipExportCreateRequest,
    ClipExportDownloadResponse,
    ClipExportResponse,
)
from app.services.clip_extraction import ClipBoundaryError, validate_clip_range
from app.services.export_storage import export_object_key
from app.services.framing import output_dimensions
from app.services.storage import StorageError, StorageService, get_storage_service
from app.services.quotas import QuotaExceededError, enforce_render_concurrency


router = APIRouter(tags=["clip exports"])
RENDER_ENGINE_VERSION = "m5-v1"


def _job(db: Session, export_id: uuid.UUID, owner_id: uuid.UUID) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.clip_export_id == export_id,
            ProcessingJob.owner_id == owner_id,
        )
    )


def _response(db: Session, export: ClipExport) -> ClipExportResponse:
    return ClipExportResponse(
        id=export.id,
        moment_id=export.moment_id,
        asset_id=export.asset_id,
        status=export.status,
        aspect_ratio=export.aspect_ratio,
        resolution=export.resolution,
        fps=export.fps,
        caption_preset=export.caption_preset,
        framing_mode=export.framing_mode,
        render_settings=export.render_settings_json,
        file_size_bytes=export.file_size_bytes,
        duration_ms=export.duration_ms,
        video_codec=export.video_codec,
        audio_codec=export.audio_codec,
        error_message=export.error_message,
        job=job_summary(_job(db, export.id, export.owner_id)),
        created_at=export.created_at,
        started_at=export.started_at,
        completed_at=export.completed_at,
    )


def _load_export(db: Session, export_id: uuid.UUID, owner_id: uuid.UUID) -> ClipExport:
    export = db.scalar(
        select(ClipExport).where(ClipExport.id == export_id, ClipExport.owner_id == owner_id)
    )
    if export is None:
        raise HTTPException(status_code=404, detail="Clip export not found")
    return export


@router.post(
    "/moments/{moment_id}/exports",
    response_model=ClipExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(
    moment_id: uuid.UUID,
    payload: ClipExportCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> ClipExportResponse:
    moment = db.scalar(
        select(MomentCandidate).where(
            MomentCandidate.id == moment_id,
            MomentCandidate.owner_id == user.id,
        )
    )
    if moment is None:
        raise HTTPException(status_code=404, detail="Moment recommendation not found")
    if moment.review_status != MomentReviewStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved moments can be exported.")
    asset = moment.asset
    if asset.duration_seconds is None or asset.width is None or asset.height is None:
        raise HTTPException(status_code=409, detail="Source media metadata is incomplete.")
    try:
        clip = validate_clip_range(
            moment.start_ms,
            moment.end_ms,
            source_duration_ms=round(asset.duration_seconds * 1000),
            maximum_duration_ms=settings.moment_max_duration_seconds * 1000,
        )
        width, height = output_dimensions(payload.aspect_ratio.value, payload.quality)
    except (ClipBoundaryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fps = min(float(payload.fps or asset.frame_rate or settings.render_fps_cap), settings.render_fps_cap)
    font_size = payload.caption_font_size or (76 if payload.quality == "1080p" else 52)
    render_settings = {
        "render_engine_version": RENDER_ENGINE_VERSION,
        "quality": payload.quality,
        "manual_crop_x": payload.manual_crop_x,
        "manual_crop_y": payload.manual_crop_y,
        "caption_font_size": font_size,
        "caption_text_color": payload.caption_text_color.upper(),
        "caption_highlight_color": payload.caption_highlight_color.upper(),
        "caption_vertical_position": payload.caption_vertical_position,
        "source_start_ms": clip.start_ms,
        "source_end_ms": clip.end_ms,
    }
    fingerprint = {
        "aspect_ratio": payload.aspect_ratio.value,
        "framing_mode": payload.framing_mode.value,
        "caption_preset": payload.caption_preset.value,
        "fps": fps,
        **render_settings,
    }
    settings_hash = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    export = db.scalar(
        select(ClipExport).where(
            ClipExport.moment_id == moment.id,
            ClipExport.owner_id == user.id,
            ClipExport.settings_hash == settings_hash,
        )
    )
    if export is not None and export.status == ClipExportStatus.COMPLETED:
        return _response(db, export)
    if export is not None and export.status in {
        ClipExportStatus.QUEUED,
        ClipExportStatus.PROCESSING,
        ClipExportStatus.RETRY,
    }:
        return _response(db, export)
    try:
        enforce_render_concurrency(db, user.id, settings)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if export is None:
        export_id = uuid.uuid4()
        export = ClipExport(
            id=export_id,
            owner_id=user.id,
            moment_id=moment.id,
            asset_id=asset.id,
            status=ClipExportStatus.QUEUED,
            aspect_ratio=payload.aspect_ratio,
            resolution=f"{width}x{height}",
            fps=fps,
            caption_preset=payload.caption_preset,
            framing_mode=payload.framing_mode,
            render_settings_json=render_settings,
            settings_hash=settings_hash,
            r2_object_key=export_object_key(asset.project_id, export_id),
            duration_ms=clip.duration_ms,
        )
        db.add(export)
        db.flush()
    elif export.status in {ClipExportStatus.FAILED, ClipExportStatus.CANCELLED}:
        export.status = ClipExportStatus.QUEUED
        export.error_message = None
        export.started_at = None
        export.completed_at = None
        export.file_size_bytes = None
        export.video_codec = None
        export.audio_codec = None

    job = _job(db, export.id, user.id)
    if job is None:
        job = ProcessingJob(
            owner_id=user.id,
            asset_id=asset.id,
            clip_export_id=export.id,
            job_type=ProcessingJobType.CLIP_RENDER,
            status=ProcessingJobStatus.QUEUED,
            max_attempts=2,
            progress_stage="queued",
        )
        db.add(job)
    elif job.status in {
        ProcessingJobStatus.FAILED,
        ProcessingJobStatus.CANCELLED,
        ProcessingJobStatus.SUCCEEDED,
    }:
        job.status = ProcessingJobStatus.QUEUED
        job.attempts = 0
        job.error_message = None
        job.progress_stage = "queued"
        job.progress_completed = None
        job.progress_total = None
        job.claimed_by = None
        job.lease_expires_at = None
        job.started_at = None
        job.finished_at = None
    db.commit()
    db.refresh(export)
    return _response(db, export)


@router.get("/moments/{moment_id}/exports", response_model=list[ClipExportResponse])
def list_exports(
    moment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> list[ClipExportResponse]:
    if db.scalar(
        select(MomentCandidate).where(
            MomentCandidate.id == moment_id, MomentCandidate.owner_id == user.id
        )
    ) is None:
        raise HTTPException(status_code=404, detail="Moment recommendation not found")
    exports = db.scalars(
        select(ClipExport)
        .where(ClipExport.moment_id == moment_id, ClipExport.owner_id == user.id)
        .order_by(ClipExport.created_at.desc())
    )
    return [_response(db, item) for item in exports]


@router.get("/exports/{export_id}", response_model=ClipExportResponse)
def get_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> ClipExportResponse:
    return _response(db, _load_export(db, export_id, user.id))


@router.get("/exports/{export_id}/download", response_model=ClipExportDownloadResponse)
def download_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> ClipExportDownloadResponse:
    export = _load_export(db, export_id, user.id)
    if export.status != ClipExportStatus.COMPLETED or not export.r2_object_key:
        raise HTTPException(status_code=409, detail="Clip export is not ready for download.")
    try:
        url = storage.generate_get_url(export.r2_object_key, settings.signed_url_expiry_seconds)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not sign the private export URL.") from exc
    return ClipExportDownloadResponse(
        export_id=export.id,
        download_url=url,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.signed_url_expiry_seconds),
    )


@router.post("/exports/{export_id}/cancel", response_model=ClipExportResponse)
def cancel_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    user: AuthenticatedUser = Depends(require_user),
) -> ClipExportResponse:
    export = _load_export(db, export_id, user.id)
    if export.status == ClipExportStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="A completed export cannot be cancelled.")
    if export.status != ClipExportStatus.CANCELLED:
        export.status = ClipExportStatus.CANCELLED
        export.error_message = "Cancelled by user."
        export.completed_at = datetime.now(timezone.utc)
        job = _job(db, export.id, user.id)
        if job is not None:
            job.status = ProcessingJobStatus.CANCELLED
            job.error_message = "Cancelled by user."
            job.progress_stage = "cancelled"
            job.claimed_by = None
            job.lease_expires_at = None
            job.finished_at = datetime.now(timezone.utc)
        db.commit()
        if export.r2_object_key:
            try:
                storage.delete_object(export.r2_object_key)
            except StorageError as exc:
                if exc.code not in {"NoSuchKey", "404"}:
                    raise HTTPException(
                        status_code=502, detail="Export was cancelled but R2 cleanup failed."
                    ) from exc
    return _response(db, export)
