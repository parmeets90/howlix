"""Add transcription persistence and durable job progress.

Revision ID: 20261029_0003
Revises: 20261029_0002
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261029_0003"
down_revision: str | None = "20261029_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("progress_stage", sa.String(64)))
    op.add_column("processing_jobs", sa.Column("progress_completed", sa.Integer()))
    op.add_column("processing_jobs", sa.Column("progress_total", sa.Integer()))

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("language", sa.String(16)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("full_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_transcripts_asset_id"),
    )
    op.create_index("ix_transcripts_status", "transcripts", ["status"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start"),
        sa.CheckConstraint("end_ms >= start_ms", name="ck_transcript_segments_range"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcript_segments_transcript_start",
        "transcript_segments",
        ["transcript_id", "start_ms"],
    )

    op.create_table(
        "transcript_words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.Uuid()),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.CheckConstraint("start_ms >= 0", name="ck_transcript_words_start"),
        sa.CheckConstraint("end_ms >= start_ms", name="ck_transcript_words_range"),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcript_words_transcript_start",
        "transcript_words",
        ["transcript_id", "start_ms"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_words_transcript_start", table_name="transcript_words")
    op.drop_table("transcript_words")
    op.drop_index("ix_transcript_segments_transcript_start", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("ix_transcripts_status", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_column("processing_jobs", "progress_total")
    op.drop_column("processing_jobs", "progress_completed")
    op.drop_column("processing_jobs", "progress_stage")
