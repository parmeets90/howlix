from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ClipExport,
    MediaAsset,
    ProcessingJob,
    ProcessingJobStatus,
    UploadSession,
    UploadSessionStatus,
)
from app.services.quotas import release_storage
from app.services.storage import StorageService


ACTIVE_UPLOAD_STATUSES = {
    UploadSessionStatus.INITIATED,
    UploadSessionStatus.UPLOADING,
}


def asset_has_active_work(db: Session, asset_id: uuid.UUID) -> bool:
    return db.scalar(
        select(ProcessingJob.id)
        .where(
            ProcessingJob.asset_id == asset_id,
            ProcessingJob.status == ProcessingJobStatus.PROCESSING,
        )
        .limit(1)
    ) is not None


def delete_asset_storage(
    db: Session, storage: StorageService, asset: MediaAsset
) -> int:
    """Delete every stored object owned by an asset and return released bytes."""
    sessions = list(
        db.scalars(select(UploadSession).where(UploadSession.asset_id == asset.id))
    )
    for session in sessions:
        if session.status in ACTIVE_UPLOAD_STATUSES:
            storage.abort_multipart_upload(asset.object_key, session.r2_upload_id)

    exports = list(
        db.scalars(select(ClipExport).where(ClipExport.asset_id == asset.id))
    )
    object_keys = {asset.object_key}
    object_keys.update(value.r2_object_key for value in exports if value.r2_object_key)
    for object_key in sorted(object_keys):
        storage.delete_object(object_key)

    return asset.file_size_bytes + sum(value.file_size_bytes or 0 for value in exports)


def delete_asset(db: Session, storage: StorageService, asset: MediaAsset) -> None:
    released_bytes = delete_asset_storage(db, storage, asset)
    release_storage(db, asset.owner_id, released_bytes)
    db.delete(asset)

