from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    MediaAssetStatus,
    MomentAnalysisStatus,
    MomentReviewStatus,
    ProcessingJobStatus,
    ProjectStatus,
    TranscriptStatus,
    UploadSessionStatus,
)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class UploadInitiateRequest(BaseModel):
    original_filename: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(min_length=1, max_length=100)
    file_size_bytes: int = Field(gt=0)


class UploadSessionResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    status: UploadSessionStatus
    part_size_bytes: int
    expected_size_bytes: int
    total_parts: int
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None


class UploadInitiateResponse(BaseModel):
    session: UploadSessionResponse


class UploadPartSignRequest(BaseModel):
    part_number: int = Field(ge=1, le=10000)


class UploadPartSignResponse(BaseModel):
    part_number: int
    upload_url: str
    expires_at: datetime


class UploadedPartResponse(BaseModel):
    part_number: int
    etag: str
    size: int


class UploadedPartsResponse(BaseModel):
    session_id: uuid.UUID
    parts: list[UploadedPartResponse]


class CompletedPartInput(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str = Field(min_length=1, max_length=256)


class CompleteUploadRequest(BaseModel):
    parts: list[CompletedPartInput] = Field(min_length=1, max_length=10000)


class UploadCompletionResponse(BaseModel):
    session: UploadSessionResponse
    asset_id: uuid.UUID
    asset_status: MediaAssetStatus
    validation_job_id: uuid.UUID | None


class ProcessingJobSummary(BaseModel):
    id: uuid.UUID
    status: ProcessingJobStatus
    attempts: int
    max_attempts: int
    error_message: str | None
    progress_stage: str | None
    progress_completed: int | None
    progress_total: int | None
    started_at: datetime | None
    finished_at: datetime | None


class MediaAssetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    duration_seconds: float | None
    width: int | None
    height: int | None
    frame_rate: float | None
    video_codec: str | None
    audio_codec: str | None
    container_format: str | None
    status: MediaAssetStatus
    created_at: datetime
    updated_at: datetime
    preview_url: str | None = None
    preview_url_expires_at: datetime | None = None
    latest_job: ProcessingJobSummary | None = None


class TranscriptWordResponse(BaseModel):
    id: uuid.UUID
    segment_id: uuid.UUID | None
    start_ms: int
    end_ms: int
    word: str
    confidence: float | None


class TranscriptSegmentResponse(BaseModel):
    id: uuid.UUID
    start_ms: int
    end_ms: int
    text: str


class TranscriptResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    provider: str
    model: str
    language: str | None
    status: TranscriptStatus
    full_text: str | None
    segments: list[TranscriptSegmentResponse]
    words: list[TranscriptWordResponse]
    created_at: datetime
    updated_at: datetime


class TranscriptionStatusResponse(BaseModel):
    asset_id: uuid.UUID
    transcript_id: uuid.UUID | None
    transcript_status: TranscriptStatus | None
    job: ProcessingJobSummary | None


class MomentAnalysisResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    transcript_id: uuid.UUID
    status: MomentAnalysisStatus
    provider: str
    model: str
    prompt_version: str
    analysis_version: str
    settings: dict
    usage: dict | None
    error_message: str | None
    recommendation_count: int
    job: ProcessingJobSummary | None
    created_at: datetime
    completed_at: datetime | None


class MomentCandidateResponse(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    asset_id: uuid.UUID
    start_ms: int
    end_ms: int
    ai_start_ms: int
    ai_end_ms: int
    duration_ms: int
    suggested_title: str
    hook_text: str
    topic: str
    category: str
    overall_score: float
    score_breakdown: dict
    explanation: str
    confidence_notes: str
    needs_context: bool
    rank: int
    review_status: MomentReviewStatus
    transcript_excerpt: str
    created_at: datetime
    updated_at: datetime


class MomentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_title: str | None = Field(default=None, min_length=1, max_length=200)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    reset_boundaries: bool = False

    @field_validator("suggested_title")
    @classmethod
    def normalize_moment_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Suggested title must not be blank")
        return value


class MomentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: MomentReviewStatus


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

