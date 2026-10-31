from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Project
from app.schemas import ErrorResponse, ProjectCreate, ProjectResponse
from app.services.quotas import QuotaExceededError, enforce_project_quota


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

