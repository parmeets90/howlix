from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.models import MediaAsset, ProcessingJob, UploadSession
from app.schemas import (
    MediaAssetResponse,
    ProcessingJobSummary,
    UploadSessionResponse,
)
from app.services.storage import StorageService


def upload_session_response(session: UploadSession) -> UploadSessionResponse:
    return UploadSessionResponse(
        id=session.id,
        asset_id=session.asset_id,
        status=session.status,
        part_size_bytes=session.part_size_bytes,
        expected_size_bytes=session.expected_size_bytes,
        total_parts=math.ceil(session.expected_size_bytes / session.part_size_bytes),
        created_at=session.created_at,
        expires_at=session.expires_at,
        completed_at=session.completed_at,
    )


def job_summary(job: ProcessingJob | None) -> ProcessingJobSummary | None:
    if job is None:
        return None
    return ProcessingJobSummary(
        id=job.id,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def media_asset_response(
    asset: MediaAsset,
    latest_job: ProcessingJob | None,
    storage: StorageService | None,
    settings: Settings,
) -> MediaAssetResponse:
    preview_url = None
    preview_expires_at = None
    if storage is not None and asset.status.value == "ready":
        preview_url = storage.generate_get_url(
            asset.object_key, settings.signed_url_expiry_seconds
        )
        preview_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.signed_url_expiry_seconds
        )
    return MediaAssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        file_size_bytes=asset.file_size_bytes,
        duration_seconds=asset.duration_seconds,
        width=asset.width,
        height=asset.height,
        frame_rate=asset.frame_rate,
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        container_format=asset.container_format,
        status=asset.status,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        preview_url=preview_url,
        preview_url_expires_at=preview_expires_at,
        latest_job=job_summary(latest_job),
    )
