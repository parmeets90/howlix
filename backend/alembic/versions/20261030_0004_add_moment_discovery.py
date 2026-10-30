"""Add durable moment analysis runs and clip recommendations.

Revision ID: 20261030_0004
Revises: 20261029_0003
Create Date: 2026-10-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261030_0004"
down_revision: str | None = "20261029_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moment_analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("analysis_version", sa.String(32), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "transcript_id",
            "analysis_version",
            "prompt_version",
            name="uq_moment_analysis_reproducible_run",
        ),
    )
    op.create_index(
        "ix_moment_analysis_asset_created",
        "moment_analysis_runs",
        ["asset_id", "created_at"],
    )
    op.create_index("ix_moment_analysis_status", "moment_analysis_runs", ["status"])

    op.create_table(
        "moment_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("ai_start_ms", sa.Integer(), nullable=False),
        sa.Column("ai_end_ms", sa.Integer(), nullable=False),
        sa.Column("suggested_title", sa.String(200), nullable=False),
        sa.Column("hook_text", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("score_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence_notes", sa.Text(), nullable=False),
        sa.Column("needs_context", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_moment_candidates_start"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_moment_candidates_range"),
        sa.CheckConstraint("ai_start_ms >= 0", name="ck_moment_candidates_ai_start"),
        sa.CheckConstraint("ai_end_ms > ai_start_ms", name="ck_moment_candidates_ai_range"),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_moment_candidates_score",
        ),
        sa.CheckConstraint("rank > 0", name="ck_moment_candidates_rank"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"], ["moment_analysis_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", "rank", name="uq_moment_candidates_run_rank"),
    )
    op.create_index(
        "ix_moment_candidates_asset_rank", "moment_candidates", ["asset_id", "rank"]
    )
    op.create_index(
        "ix_moment_candidates_review_status", "moment_candidates", ["review_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_moment_candidates_review_status", table_name="moment_candidates")
    op.drop_index("ix_moment_candidates_asset_rank", table_name="moment_candidates")
    op.drop_table("moment_candidates")
    op.drop_index("ix_moment_analysis_status", table_name="moment_analysis_runs")
    op.drop_index("ix_moment_analysis_asset_created", table_name="moment_analysis_runs")
    op.drop_table("moment_analysis_runs")
