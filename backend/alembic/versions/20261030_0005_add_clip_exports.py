"""Add durable clip exports and render-job linkage.

Revision ID: 20261030_0005
Revises: 20261030_0004
Create Date: 2026-10-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261030_0005"
down_revision: str | None = "20261030_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clip_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("moment_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("aspect_ratio", sa.String(16), nullable=False),
        sa.Column("resolution", sa.String(32), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("caption_preset", sa.String(32), nullable=False),
        sa.Column("framing_mode", sa.String(32), nullable=False),
        sa.Column("render_settings_json", sa.JSON(), nullable=False),
        sa.Column("settings_hash", sa.String(64), nullable=False),
        sa.Column("r2_object_key", sa.String(512)),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("video_codec", sa.String(64)),
        sa.Column("audio_codec", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("duration_ms > 0", name="ck_clip_exports_duration"),
        sa.CheckConstraint("fps > 0 AND fps <= 60", name="ck_clip_exports_fps"),
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes > 0",
            name="ck_clip_exports_file_size",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moment_id"], ["moment_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("moment_id", "settings_hash", name="uq_clip_exports_settings"),
    )
    op.create_index(
        "ix_clip_exports_moment_created", "clip_exports", ["moment_id", "created_at"]
    )
    op.create_index(
        "ix_clip_exports_asset_status", "clip_exports", ["asset_id", "status"]
    )

    op.add_column("processing_jobs", sa.Column("clip_export_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_processing_jobs_clip_export",
        "processing_jobs",
        "clip_exports",
        ["clip_export_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_processing_jobs_asset_job_type", "processing_jobs", type_="unique"
    )
    op.create_index(
        "uq_processing_jobs_asset_job_type",
        "processing_jobs",
        ["asset_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("clip_export_id IS NULL"),
    )
    op.create_index(
        "uq_processing_jobs_clip_export",
        "processing_jobs",
        ["clip_export_id"],
        unique=True,
        postgresql_where=sa.text("clip_export_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_processing_jobs_clip_export", table_name="processing_jobs")
    op.drop_index("uq_processing_jobs_asset_job_type", table_name="processing_jobs")
    op.create_unique_constraint(
        "uq_processing_jobs_asset_job_type",
        "processing_jobs",
        ["asset_id", "job_type"],
    )
    op.drop_constraint(
        "fk_processing_jobs_clip_export", "processing_jobs", type_="foreignkey"
    )
    op.drop_column("processing_jobs", "clip_export_id")
    op.drop_index("ix_clip_exports_asset_status", table_name="clip_exports")
    op.drop_index("ix_clip_exports_moment_created", table_name="clip_exports")
    op.drop_table("clip_exports")
