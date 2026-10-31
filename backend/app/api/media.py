from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import media_asset_response
from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import MediaAsset, ProcessingJob, Project
from app.schemas import MediaAssetResponse
from app.services.storage import StorageError, StorageService, get_storage_service


router = APIRouter(tags=["media"])


def _latest_job(
    db: Session, asset_id: uuid.UUID, owner_id: uuid.UUID
) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.asset_id == asset_id, ProcessingJob.owner_id == owner_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


@router.get(
    "/projects/{project_id}/media", response_model=list[MediaAssetResponse]
)
def list_project_media(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> list[MediaAssetResponse]:
    if db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    assets = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.project_id == project_id, MediaAsset.owner_id == user.id)
            .order_by(MediaAsset.created_at.desc())
        )
    )
    try:
        return [
            media_asset_response(asset, _latest_job(db, asset.id, user.id), storage, settings)
            for asset in assets
        ]
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not sign the private preview URL.") from exc


@router.get("/media/{asset_id}", response_model=MediaAssetResponse)
def get_media_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> MediaAssetResponse:
    asset = db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id)
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    try:
        return media_asset_response(asset, _latest_job(db, asset.id, user.id), storage, settings)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not sign the private preview URL.") from exc
