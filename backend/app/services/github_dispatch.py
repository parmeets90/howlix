from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    JobDispatchStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
)


logger = logging.getLogger("howlix.github_dispatch")
SUPPORTED_JOB_TYPES = frozenset(ProcessingJobType)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class DispatchResult(str, Enum):
    DISABLED = "disabled"
    DISPATCHED = "dispatched"
    ALREADY_DISPATCHED = "already_dispatched"
    INELIGIBLE = "ineligible"
    CAP_REACHED = "cap_reached"
    FAILED = "failed"


def _eligible(job: ProcessingJob, now: datetime) -> bool:
    if job.owner_id is None or job.job_type not in SUPPORTED_JOB_TYPES:
        return False
    if job.attempts >= job.max_attempts:
        return False
    if job.status == ProcessingJobStatus.QUEUED:
        return True
    return (
        job.status == ProcessingJobStatus.RETRY
        and (job.lease_expires_at is None or job.lease_expires_at <= now)
    )


def dispatch_job(
    db: Session,
    job_id: uuid.UUID,
    settings: Settings,
    *,
    owner_id: uuid.UUID | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> DispatchResult:
    """Dispatch one eligible persisted job without exposing GitHub credentials."""
    if not settings.github_actions_dispatch_enabled:
        return DispatchResult.DISABLED
    if settings.github_actions_token is None:
        return DispatchResult.FAILED

    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=settings.github_runner_startup_timeout_seconds)
    job = db.scalar(
        select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
    )
    if job is None or (owner_id is not None and job.owner_id != owner_id) or not _eligible(job, now):
        db.rollback()
        return DispatchResult.INELIGIBLE

    still_starting = (
        job.dispatch_status in {JobDispatchStatus.DISPATCHING, JobDispatchStatus.DISPATCHED}
        and _utc(job.dispatched_at) is not None
        and _utc(job.dispatched_at) > stale_before
    )
    if still_starting and not force:
        db.rollback()
        return DispatchResult.ALREADY_DISPATCHED
    if job.dispatch_attempts >= settings.github_dispatch_max_attempts and not force:
        job.dispatch_status = JobDispatchStatus.FAILED
        job.dispatch_error_message = "GitHub runner dispatch retry limit reached."
        job.progress_stage = "dispatch_failed"
        db.commit()
        return DispatchResult.FAILED

    active = db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.id != job.id,
            or_(
                ProcessingJob.claimed_by.like("gha-%"),
                (
                    ProcessingJob.dispatch_status.in_(
                        [JobDispatchStatus.DISPATCHING, JobDispatchStatus.DISPATCHED]
                    )
                    & (ProcessingJob.dispatched_at > stale_before)
                ),
            ),
            ProcessingJob.status.in_(
                [
                    ProcessingJobStatus.QUEUED,
                    ProcessingJobStatus.RETRY,
                    ProcessingJobStatus.PROCESSING,
                ]
            ),
        )
    ) or 0
    if active >= settings.github_actions_max_active_jobs:
        job.dispatch_status = JobDispatchStatus.PENDING
        job.dispatch_error_message = "Private-beta runner concurrency cap is currently reached."
        job.progress_stage = "waiting_runner_capacity"
        db.commit()
        return DispatchResult.CAP_REACHED

    job.dispatch_status = JobDispatchStatus.DISPATCHING
    job.dispatch_attempts += 1
    job.dispatch_requested_at = now
    job.dispatched_at = now
    job.dispatch_error_message = None
    db.commit()

    url = (
        f"https://api.github.com/repos/{settings.github_repository}/actions/workflows/"
        f"{settings.github_worker_workflow}/dispatches"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_actions_token.get_secret_value()}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": settings.github_worker_ref, "inputs": {"job_id": str(job_id)}}
    owns_client = client is None
    http = client or httpx.Client(timeout=settings.github_dispatch_timeout_seconds)
    error = "GitHub rejected the workflow dispatch."
    try:
        for attempt in range(settings.github_dispatch_max_attempts):
            try:
                response = http.post(url, headers=headers, json=payload)
                if response.status_code == 204:
                    job = db.get(ProcessingJob, job_id)
                    if job is None:
                        return DispatchResult.INELIGIBLE
                    job.dispatch_status = JobDispatchStatus.DISPATCHED
                    job.dispatched_at = datetime.now(timezone.utc)
                    job.dispatch_error_message = None
                    job.progress_stage = "starting_runner"
                    db.commit()
                    return DispatchResult.DISPATCHED
                error = f"GitHub workflow dispatch returned HTTP {response.status_code}."
                if response.status_code not in {408, 429, 500, 502, 503, 504}:
                    break
            except httpx.HTTPError as exc:
                error = f"GitHub workflow dispatch failed: {type(exc).__name__}."
            if attempt + 1 < settings.github_dispatch_max_attempts:
                sleep(min(4.0, 0.5 * (2**attempt)))
    finally:
        if owns_client:
            http.close()

    job = db.get(ProcessingJob, job_id)
    if job is not None:
        job.dispatch_status = JobDispatchStatus.FAILED
        job.dispatch_error_message = error[:1000]
        job.progress_stage = "dispatch_failed"
        db.commit()
    logger.warning("GitHub workflow dispatch failed: %s", error)
    return DispatchResult.FAILED
