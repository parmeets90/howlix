from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.responses import job_summary
from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import ProcessingJob
from app.schemas import ProcessingJobSummary
from app.services.github_dispatch import DispatchResult, dispatch_job


router = APIRouter(tags=["jobs"])


@router.post(
    "/jobs/{job_id}/dispatch",
    response_model=ProcessingJobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def recover_job_dispatch(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> ProcessingJobSummary:
    job = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.owner_id == user.id
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    result = dispatch_job(db, job.id, settings, owner_id=user.id)
    if result == DispatchResult.DISABLED:
        raise HTTPException(status_code=503, detail="GitHub Actions dispatch is not enabled.")
    if result == DispatchResult.INELIGIBLE:
        raise HTTPException(status_code=409, detail="This job is not eligible for dispatch.")
    if result == DispatchResult.CAP_REACHED:
        raise HTTPException(status_code=429, detail="The private-beta runner limit is busy.")
    if result == DispatchResult.FAILED:
        raise HTTPException(status_code=502, detail="Could not start the processing runner.")
    db.refresh(job)
    value = job_summary(job)
    assert value is not None
    return value
