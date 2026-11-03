from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import MediaAsset, Project
from app.schemas import ErrorResponse, ProjectCreate, ProjectResponse
from app.services.quotas import QuotaExceededError, enforce_project_quota
from app.services.deletion import asset_has_active_work, delete_asset
from app.services.storage import StorageError, StorageService, get_storage_service


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db), user: AuthenticatedUser = Depends(require_user)
) -> list[Project]:
    statement = (
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return list(db.scalars(statement))


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> Project:
    try:
        enforce_project_quota(db, user.id, settings)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    project = Project(owner_id=user.id, title=payload.title, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    user: AuthenticatedUser = Depends(require_user),
) -> Response:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    assets = list(
        db.scalars(
            select(MediaAsset).where(
                MediaAsset.project_id == project.id,
                MediaAsset.owner_id == user.id,
            )
        )
    )
    if any(asset_has_active_work(db, asset.id) for asset in assets):
        raise HTTPException(
            status_code=409,
            detail="A video in this project is still being prepared. Please wait a moment and try again.",
        )
    try:
        for asset in assets:
            delete_asset(db, storage, asset)
        db.delete(project)
        db.commit()
    except StorageError as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="The project files could not be removed from storage. Please try again.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

