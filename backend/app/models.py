from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"


class MediaAssetStatus(str, enum.Enum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"
    ABORTED = "aborted"


class UploadSessionStatus(str, enum.Enum):
    INITIATED = "initiated"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    ABORTED = "aborted"
    EXPIRED = "expired"
    FAILED = "failed"


class ProcessingJobType(str, enum.Enum):
    VALIDATE_MEDIA = "validate_media"
    TRANSCRIBE_MEDIA = "transcribe_media"
    MOMENT_DISCOVERY = "moment_discovery"


class ProcessingJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TranscriptStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"


class MomentAnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"


class MomentReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def enum_type(enum_class: type[enum.Enum], length: int = 32) -> Enum:
    return Enum(
        enum_class,
        native_enum=False,
        length=length,
        values_callable=lambda values: [value.value for value in values],
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_type(ProjectStatus),
        nullable=False,
        default=ProjectStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="ck_media_assets_file_size_positive"),
        UniqueConstraint("object_key", name="uq_media_assets_object_key"),
        Index("ix_media_assets_project_created", "project_id", "created_at"),
        Index("ix_media_assets_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    container_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[MediaAssetStatus] = mapped_column(
        enum_type(MediaAssetStatus), nullable=False, default=MediaAssetStatus.PENDING_UPLOAD
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    project: Mapped[Project] = relationship(back_populates="media_assets")
    upload_sessions: Mapped[list["UploadSession"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="asset", cascade="all, delete-orphan", uselist=False
    )
    moment_analysis_runs: Mapped[list["MomentAnalysisRun"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    moment_candidates: Mapped[list["MomentCandidate"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint("part_size_bytes >= 5242880", name="ck_upload_sessions_part_size"),
        CheckConstraint("expected_size_bytes > 0", name="ck_upload_sessions_expected_size"),
        UniqueConstraint("asset_id", name="uq_upload_sessions_asset_id"),
        Index("ix_upload_sessions_status_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    r2_upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[UploadSessionStatus] = mapped_column(
        enum_type(UploadSessionStatus),
        nullable=False,
        default=UploadSessionStatus.INITIATED,
    )
    part_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped[MediaAsset] = relationship(back_populates="upload_sessions")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_processing_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_processing_jobs_max_attempts_positive"),
        UniqueConstraint("asset_id", "job_type", name="uq_processing_jobs_asset_job_type"),
        Index("ix_processing_jobs_claim", "status", "lease_expires_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[ProcessingJobType] = mapped_column(
        enum_type(ProcessingJobType), nullable=False
    )
    status: Mapped[ProcessingJobStatus] = mapped_column(
        enum_type(ProcessingJobStatus), nullable=False, default=ProcessingJobStatus.QUEUED
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    asset: Mapped[MediaAsset] = relationship(back_populates="processing_jobs")


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_transcripts_asset_id"),
        Index("ix_transcripts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[TranscriptStatus] = mapped_column(
        enum_type(TranscriptStatus), nullable=False, default=TranscriptStatus.QUEUED
    )
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    asset: Mapped[MediaAsset] = relationship(back_populates="transcript")
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.start_ms",
    )
    words: Mapped[list["TranscriptWord"]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptWord.start_ms",
    )
    moment_analysis_runs: Mapped[list["MomentAnalysisRun"]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start"),
        CheckConstraint("end_ms >= start_ms", name="ck_transcript_segments_range"),
        Index("ix_transcript_segments_transcript_start", "transcript_id", "start_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")
    words: Mapped[list["TranscriptWord"]] = relationship(back_populates="segment")


class TranscriptWord(Base):
    __tablename__ = "transcript_words"
    __table_args__ = (
        CheckConstraint("start_ms >= 0", name="ck_transcript_words_start"),
        CheckConstraint("end_ms >= start_ms", name="ck_transcript_words_range"),
        Index("ix_transcript_words_transcript_start", "transcript_id", "start_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transcript_segments.id", ondelete="SET NULL"), nullable=True
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcript: Mapped[Transcript] = relationship(back_populates="words")
    segment: Mapped[TranscriptSegment | None] = relationship(back_populates="words")


class MomentAnalysisRun(Base):
    __tablename__ = "moment_analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "transcript_id",
            "analysis_version",
            "prompt_version",
            name="uq_moment_analysis_reproducible_run",
        ),
        Index("ix_moment_analysis_asset_created", "asset_id", "created_at"),
        Index("ix_moment_analysis_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MomentAnalysisStatus] = mapped_column(
        enum_type(MomentAnalysisStatus), nullable=False, default=MomentAnalysisStatus.QUEUED
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    usage_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped[MediaAsset] = relationship(back_populates="moment_analysis_runs")
    transcript: Mapped[Transcript] = relationship(back_populates="moment_analysis_runs")
    candidates: Mapped[list["MomentCandidate"]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        order_by="MomentCandidate.rank",
    )


class MomentCandidate(Base):
    __tablename__ = "moment_candidates"
    __table_args__ = (
        CheckConstraint("start_ms >= 0", name="ck_moment_candidates_start"),
        CheckConstraint("end_ms > start_ms", name="ck_moment_candidates_range"),
        CheckConstraint("ai_start_ms >= 0", name="ck_moment_candidates_ai_start"),
        CheckConstraint("ai_end_ms > ai_start_ms", name="ck_moment_candidates_ai_range"),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_moment_candidates_score",
        ),
        CheckConstraint("rank > 0", name="ck_moment_candidates_rank"),
        UniqueConstraint("analysis_run_id", "rank", name="uq_moment_candidates_run_rank"),
        Index("ix_moment_candidates_asset_rank", "asset_id", "rank"),
        Index("ix_moment_candidates_review_status", "review_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("moment_analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_title: Mapped[str] = mapped_column(String(200), nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_notes: Mapped[str] = mapped_column(Text, nullable=False)
    needs_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[MomentReviewStatus] = mapped_column(
        enum_type(MomentReviewStatus), nullable=False, default=MomentReviewStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    analysis_run: Mapped[MomentAnalysisRun] = relationship(back_populates="candidates")
    asset: Mapped[MediaAsset] = relationship(back_populates="moment_candidates")

