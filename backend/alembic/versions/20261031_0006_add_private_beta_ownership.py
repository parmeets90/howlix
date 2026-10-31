"""Add private-beta ownership and durable quota usage.

Revision ID: 20261031_0006
Revises: 20261030_0005
Create Date: 2026-10-31

Existing rows intentionally retain NULL owner_id values. They are quarantined from
authenticated API queries until an operator explicitly assigns the correct user.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261031_0006"
down_revision: str | None = "20261030_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OWNED_TABLES = (
    "projects",
    "media_assets",
    "upload_sessions",
    "processing_jobs",
    "transcripts",
    "moment_analysis_runs",
    "moment_candidates",
    "clip_exports",
)


def upgrade() -> None:
    for table_name in OWNED_TABLES:
        op.add_column(table_name, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.create_index(f"ix_{table_name}_owner_id", table_name, ["owner_id"])

    op.create_table(
        "user_usage",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("stored_media_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stored_media_bytes >= 0", name="ck_user_usage_storage_nonnegative"
        ),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.create_table(
        "user_monthly_usage",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("transcription_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transcription_seconds >= 0",
            name="ck_user_monthly_transcription_nonnegative",
        ),
        sa.CheckConstraint(
            "analysis_jobs >= 0", name="ck_user_monthly_analysis_nonnegative"
        ),
        sa.PrimaryKeyConstraint("owner_id", "period_start"),
    )


def downgrade() -> None:
    op.drop_table("user_monthly_usage")
    op.drop_table("user_usage")
    for table_name in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table_name}_owner_id", table_name=table_name)
        op.drop_column(table_name, "owner_id")
