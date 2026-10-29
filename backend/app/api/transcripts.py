from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.responses import job_summary
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Transcript,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptWord,
)
from app.schemas import (
    TranscriptResponse,
    TranscriptSegmentResponse,
    TranscriptionStatusResponse,
    TranscriptWordResponse,
)


router = APIRouter(tags=["transcription"])


def _transcript_response(transcript: Transcript) -> TranscriptResponse:
    return TranscriptResponse(
        id=transcript.id,
        asset_id=transcript.asset_id,
        provider=transcript.provider,
        model=transcript.model,
        language=transcript.language,
        status=transcript.status,
        full_text=transcript.full_text,
        segments=[
            TranscriptSegmentResponse(
                id=segment.id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
            )
            for segment in transcript.segments
        ],
        words=[
            TranscriptWordResponse(
                id=word.id,
                segment_id=word.segment_id,
                start_ms=word.start_ms,
                end_ms=word.end_ms,
                word=word.word,
                confidence=word.confidence,
            )
            for word in transcript.words
        ],
        created_at=transcript.created_at,
        updated_at=transcript.updated_at,
    )


def _get_transcript(db: Session, asset_id: uuid.UUID) -> Transcript | None:
    return db.scalar(
        select(Transcript)
        .where(Transcript.asset_id == asset_id)
        .options(
            selectinload(Transcript.segments),
            selectinload(Transcript.words),
        )
    )


def _get_job(db: Session, asset_id: uuid.UUID) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.asset_id == asset_id,
            ProcessingJob.job_type == ProcessingJobType.TRANSCRIBE_MEDIA,
        )
    )


@router.post(
    "/media/{asset_id}/transcribe",
    response_model=TranscriptionStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_transcription(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TranscriptionStatusResponse:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.status != MediaAssetStatus.READY:
        raise HTTPException(status_code=409, detail="Media must be validated before transcription.")
    if not asset.audio_codec:
        raise HTTPException(status_code=409, detail="This video has no supported audio stream.")
    if settings.transcription_provider == "groq" and settings.groq_api_key is None:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")

    transcript = _get_transcript(db, asset_id)
    job = _get_job(db, asset_id)
    provider = settings.transcription_provider
    model = (
        settings.groq_transcription_model
        if provider == "groq"
        else settings.faster_whisper_model
    )
    if transcript is None:
        transcript = Transcript(
            asset_id=asset_id,
            provider=provider,
            model=model,
            status=TranscriptStatus.QUEUED,
        )
        db.add(transcript)
    elif transcript.status == TranscriptStatus.COMPLETED:
        return TranscriptionStatusResponse(
            asset_id=asset_id,
            transcript_id=transcript.id,
            transcript_status=transcript.status,
            job=job_summary(job),
        )
    elif transcript.status == TranscriptStatus.FAILED:
        transcript.status = TranscriptStatus.QUEUED
        transcript.provider = provider
        transcript.model = model

    if job is None:
        job = ProcessingJob(
            asset_id=asset_id,
            job_type=ProcessingJobType.TRANSCRIBE_MEDIA,
            status=ProcessingJobStatus.QUEUED,
            progress_stage="queued",
        )
        db.add(job)
    elif job.status == ProcessingJobStatus.FAILED:
        job.status = ProcessingJobStatus.QUEUED
        job.attempts = 0
        job.error_message = None
        job.finished_at = None
        job.progress_stage = "queued"
        job.progress_completed = None
        job.progress_total = None

    db.commit()
    db.refresh(transcript)
    db.refresh(job)
    return TranscriptionStatusResponse(
        asset_id=asset_id,
        transcript_id=transcript.id,
        transcript_status=transcript.status,
        job=job_summary(job),
    )


@router.get("/media/{asset_id}/transcript", response_model=TranscriptResponse)
def get_transcript(asset_id: uuid.UUID, db: Session = Depends(get_db)) -> TranscriptResponse:
    if db.get(MediaAsset, asset_id) is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    transcript = _get_transcript(db, asset_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return _transcript_response(transcript)


@router.get(
    "/media/{asset_id}/transcription-status",
    response_model=TranscriptionStatusResponse,
)
def get_transcription_status(
    asset_id: uuid.UUID, db: Session = Depends(get_db)
) -> TranscriptionStatusResponse:
    if db.get(MediaAsset, asset_id) is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    transcript = _get_transcript(db, asset_id)
    job = _get_job(db, asset_id)
    return TranscriptionStatusResponse(
        asset_id=asset_id,
        transcript_id=transcript.id if transcript else None,
        transcript_status=transcript.status if transcript else None,
        job=job_summary(job),
    )
