"""Add media assets, multipart upload sessions, and processing jobs.

Revision ID: 20261029_0002
Revises: 20261029_0001
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261029_0002"
down_revision: str | None = "20261029_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("bucket_name", sa.String(length=128), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("frame_rate", sa.Float(), nullable=True),
        sa.Column("video_codec", sa.String(length=64), nullable=True),
        sa.Column("audio_codec", sa.String(length=64), nullable=True),
        sa.Column("container_format", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes > 0", name="ck_media_assets_file_size_positive"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_media_assets_object_key"),
    )
    op.create_index(
        "ix_media_assets_project_created",
        "media_assets",
        ["project_id", "created_at"],
    )
    op.create_index("ix_media_assets_status", "media_assets", ["status"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("r2_upload_id", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("part_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "part_size_bytes >= 5242880", name="ck_upload_sessions_part_size"
        ),
        sa.CheckConstraint(
            "expected_size_bytes > 0", name="ck_upload_sessions_expected_size"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_upload_sessions_asset_id"),
    )
    op.create_index(
        "ix_upload_sessions_status_expires",
        "upload_sessions",
        ["status", "expires_at"],
    )

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_processing_jobs_attempts_nonnegative"
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="ck_processing_jobs_max_attempts_positive"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "job_type", name="uq_processing_jobs_asset_job_type"
        ),
    )
    op.create_index(
        "ix_processing_jobs_claim",
        "processing_jobs",
        ["status", "lease_expires_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_upload_sessions_status_expires", table_name="upload_sessions")
    op.drop_table("upload_sessions")
    op.drop_index("ix_media_assets_status", table_name="media_assets")
    op.drop_index("ix_media_assets_project_created", table_name="media_assets")
    op.drop_table("media_assets")
