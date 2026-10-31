from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import job_summary
from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    MomentAnalysisRun,
    MomentAnalysisStatus,
    MomentCandidate,
    MomentReviewStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Transcript,
    TranscriptStatus,
)
from app.schemas import (
    MomentAnalysisResponse,
    MomentCandidateResponse,
    MomentReviewRequest,
    MomentUpdateRequest,
)
from app.services.quotas import QuotaExceededError, consume_analysis
from app.services.github_dispatch import dispatch_job


router = APIRouter(tags=["moment discovery"])


def _analysis_job(
    db: Session, asset_id: uuid.UUID, owner_id: uuid.UUID
) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.asset_id == asset_id,
            ProcessingJob.owner_id == owner_id,
            ProcessingJob.job_type == ProcessingJobType.MOMENT_DISCOVERY,
        )
    )


def _latest_run(
    db: Session, asset_id: uuid.UUID, owner_id: uuid.UUID
) -> MomentAnalysisRun | None:
    return db.scalar(
        select(MomentAnalysisRun)
        .where(
            MomentAnalysisRun.asset_id == asset_id,
            MomentAnalysisRun.owner_id == owner_id,
        )
        .options(selectinload(MomentAnalysisRun.candidates))
        .order_by(MomentAnalysisRun.created_at.desc())
        .limit(1)
    )


def _analysis_response(db: Session, run: MomentAnalysisRun) -> MomentAnalysisResponse:
    return MomentAnalysisResponse(
        id=run.id,
        asset_id=run.asset_id,
        transcript_id=run.transcript_id,
        status=run.status,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        analysis_version=run.analysis_version,
        settings=run.settings_json,
        usage=run.usage_json,
        error_message=run.error_message,
        recommendation_count=len(run.candidates),
        job=job_summary(_analysis_job(db, run.asset_id, run.owner_id)),
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _excerpt(db: Session, candidate: MomentCandidate) -> str:
    transcript = db.scalar(
        select(Transcript)
        .where(
            Transcript.id == candidate.analysis_run.transcript_id,
            Transcript.owner_id == candidate.owner_id,
        )
        .options(selectinload(Transcript.segments))
    )
    if transcript is None:
        return ""
    return " ".join(
        segment.text.strip()
        for segment in transcript.segments
        if segment.end_ms >= candidate.start_ms and segment.start_ms <= candidate.end_ms
    ).strip()


def _candidate_response(db: Session, candidate: MomentCandidate) -> MomentCandidateResponse:
    return MomentCandidateResponse(
        id=candidate.id,
        analysis_run_id=candidate.analysis_run_id,
        asset_id=candidate.asset_id,
        start_ms=candidate.start_ms,
        end_ms=candidate.end_ms,
        ai_start_ms=candidate.ai_start_ms,
        ai_end_ms=candidate.ai_end_ms,
        duration_ms=candidate.end_ms - candidate.start_ms,
        suggested_title=candidate.suggested_title,
        hook_text=candidate.hook_text,
        topic=candidate.topic,
        category=candidate.category,
        overall_score=candidate.overall_score,
        score_breakdown=candidate.score_breakdown_json,
        explanation=candidate.explanation,
        confidence_notes=candidate.confidence_notes,
        needs_context=candidate.needs_context,
        rank=candidate.rank,
        review_status=candidate.review_status,
        transcript_excerpt=_excerpt(db, candidate),
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _load_candidate(
    db: Session, moment_id: uuid.UUID, owner_id: uuid.UUID
) -> MomentCandidate:
    candidate = db.scalar(
        select(MomentCandidate)
        .where(MomentCandidate.id == moment_id, MomentCandidate.owner_id == owner_id)
        .options(selectinload(MomentCandidate.analysis_run))
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Moment recommendation not found")
    return candidate


@router.post(
    "/media/{asset_id}/discover-moments",
    response_model=MomentAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def discover_moments(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> MomentAnalysisResponse:
    asset = db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id)
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.status != MediaAssetStatus.READY:
        raise HTTPException(status_code=409, detail="Media must be ready before moment discovery.")
    transcript = db.scalar(
        select(Transcript).where(
            Transcript.asset_id == asset_id, Transcript.owner_id == user.id
        )
    )
    if transcript is None or transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="A completed transcript is required.")
    if settings.moment_analysis_provider == "groq" and settings.groq_api_key is None:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")

    run = db.scalar(
        select(MomentAnalysisRun)
        .where(
            MomentAnalysisRun.asset_id == asset_id,
            MomentAnalysisRun.owner_id == user.id,
            MomentAnalysisRun.transcript_id == transcript.id,
            MomentAnalysisRun.analysis_version == settings.moment_analysis_version,
            MomentAnalysisRun.prompt_version == settings.moment_prompt_version,
        )
        .options(selectinload(MomentAnalysisRun.candidates))
    )
    provider = settings.moment_analysis_provider
    model = settings.groq_moment_model if provider == "groq" else "deterministic-v1"
    if run is None:
        try:
            consume_analysis(db, user.id, settings)
        except QuotaExceededError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        run = MomentAnalysisRun(
            owner_id=user.id,
            asset_id=asset_id,
            transcript_id=transcript.id,
            status=MomentAnalysisStatus.QUEUED,
            provider=provider,
            model=model,
            prompt_version=settings.moment_prompt_version,
            analysis_version=settings.moment_analysis_version,
            settings_json={
                "minimum_duration_seconds": settings.moment_min_duration_seconds,
                "maximum_duration_seconds": settings.moment_max_duration_seconds,
                "target_duration_seconds": settings.moment_target_duration_seconds,
                "maximum_candidates": settings.moment_max_candidates,
                "maximum_recommendations": settings.moment_max_recommendations,
                "minimum_editorial_score": settings.moment_min_editorial_score,
            },
        )
        db.add(run)
    elif run.status == MomentAnalysisStatus.COMPLETED:
        return _analysis_response(db, run)
    elif run.status == MomentAnalysisStatus.FAILED:
        run.status = MomentAnalysisStatus.QUEUED
        run.error_message = None
        run.completed_at = None
        run.provider = provider
        run.model = model

    job = _analysis_job(db, asset_id, user.id)
    if job is None:
        job = ProcessingJob(
            owner_id=user.id,
            asset_id=asset_id,
            job_type=ProcessingJobType.MOMENT_DISCOVERY,
            status=ProcessingJobStatus.QUEUED,
            progress_stage="queued",
        )
        db.add(job)
    elif job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.SUCCEEDED}:
        job.status = ProcessingJobStatus.QUEUED
        job.attempts = 0
        job.error_message = None
        job.finished_at = None
        job.progress_stage = "queued"
        job.progress_completed = None
        job.progress_total = None
    db.commit()
    db.refresh(run)
    dispatch_job(db, job.id, settings, owner_id=user.id)
    return _analysis_response(db, run)


@router.get("/media/{asset_id}/moment-analysis", response_model=MomentAnalysisResponse)
def get_moment_analysis(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> MomentAnalysisResponse:
    if db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    run = _latest_run(db, asset_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Moment analysis not found")
    return _analysis_response(db, run)


@router.get("/media/{asset_id}/moments", response_model=list[MomentCandidateResponse])
def list_moments(
    asset_id: uuid.UUID,
    review_status: MomentReviewStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> list[MomentCandidateResponse]:
    if db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    run = _latest_run(db, asset_id, user.id)
    if run is None:
        return []
    statement = (
        select(MomentCandidate)
        .where(
            MomentCandidate.analysis_run_id == run.id,
            MomentCandidate.owner_id == user.id,
        )
        .options(selectinload(MomentCandidate.analysis_run))
        .order_by(MomentCandidate.rank.asc())
    )
    if review_status is not None:
        statement = statement.where(MomentCandidate.review_status == review_status)
    return [_candidate_response(db, item) for item in db.scalars(statement)]


@router.get("/moments/{moment_id}", response_model=MomentCandidateResponse)
def get_moment(
    moment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> MomentCandidateResponse:
    return _candidate_response(db, _load_candidate(db, moment_id, user.id))


def _validate_boundaries(
    db: Session,
    candidate: MomentCandidate,
    start_ms: int,
    end_ms: int,
    settings: Settings,
) -> None:
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == candidate.asset_id,
            MediaAsset.owner_id == candidate.owner_id,
        )
    )
    transcript = db.scalar(
        select(Transcript)
        .where(
            Transcript.id == candidate.analysis_run.transcript_id,
            Transcript.owner_id == candidate.owner_id,
        )
        .options(selectinload(Transcript.segments))
    )
    if asset is None or transcript is None or asset.duration_seconds is None:
        raise HTTPException(status_code=409, detail="Media timing metadata is unavailable.")
    duration_ms = end_ms - start_ms
    if end_ms <= start_ms:
        raise HTTPException(status_code=422, detail="Moment end must be after its start.")
    if duration_ms < settings.moment_min_duration_seconds * 1000:
        raise HTTPException(status_code=422, detail="Moment is shorter than the configured minimum.")
    if duration_ms > settings.moment_max_duration_seconds * 1000:
        raise HTTPException(status_code=422, detail="Moment exceeds the configured maximum.")
    source_duration_ms = round(asset.duration_seconds * 1000)
    if start_ms < 0 or end_ms > source_duration_ms:
        raise HTTPException(status_code=422, detail="Moment boundaries exceed the source video.")
    overlapping = [
        segment
        for segment in transcript.segments
        if segment.end_ms >= start_ms and segment.start_ms <= end_ms
    ]
    if not overlapping:
        raise HTTPException(status_code=422, detail="Moment boundaries do not contain transcript speech.")
    first_ms = transcript.segments[0].start_ms if transcript.segments else 0
    last_ms = transcript.segments[-1].end_ms if transcript.segments else 0
    if start_ms < max(0, first_ms - 2000) or end_ms > min(source_duration_ms, last_ms + 2000):
        raise HTTPException(status_code=422, detail="Moment boundaries are too far outside transcript timing.")


@router.patch("/moments/{moment_id}", response_model=MomentCandidateResponse)
def update_moment(
    moment_id: uuid.UUID,
    payload: MomentUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_user),
) -> MomentCandidateResponse:
    candidate = _load_candidate(db, moment_id, user.id)
    if payload.reset_boundaries:
        start_ms, end_ms = candidate.ai_start_ms, candidate.ai_end_ms
    else:
        start_ms = payload.start_ms if payload.start_ms is not None else candidate.start_ms
        end_ms = payload.end_ms if payload.end_ms is not None else candidate.end_ms
    _validate_boundaries(db, candidate, start_ms, end_ms, settings)
    candidate.start_ms = start_ms
    candidate.end_ms = end_ms
    if payload.suggested_title is not None:
        candidate.suggested_title = payload.suggested_title
    db.commit()
    db.refresh(candidate)
    return _candidate_response(db, candidate)


@router.post("/moments/{moment_id}/review", response_model=MomentCandidateResponse)
def review_moment(
    moment_id: uuid.UUID,
    payload: MomentReviewRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
) -> MomentCandidateResponse:
    candidate = _load_candidate(db, moment_id, user.id)
    candidate.review_status = payload.review_status
    db.commit()
    db.refresh(candidate)
    return _candidate_response(db, candidate)
