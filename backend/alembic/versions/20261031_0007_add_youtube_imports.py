"""Add durable, owner-scoped YouTube imports.

Revision ID: 20261031_0007
Revises: 20261031_0006
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261031_0007"
down_revision: str | None = "20261031_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "youtube_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("canonical_url", sa.String(length=512), nullable=False),
        sa.Column("video_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("permission_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reservation_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("channel_name", sa.String(length=255), nullable=True),
        sa.Column("channel_id", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.String(length=32), nullable=True),
        sa.Column("source_duration_seconds", sa.Float(), nullable=True),
        sa.Column("extractor", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("reserved_bytes > 0", name="ck_youtube_imports_reserved_positive"),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_youtube_imports_asset_id"),
        sa.UniqueConstraint(
            "owner_id", "project_id", "video_id", name="uq_youtube_imports_owner_project_video"
        ),
    )
    op.create_index("ix_youtube_imports_owner_id", "youtube_imports", ["owner_id"])
    op.create_index(
        "ix_youtube_imports_owner_status", "youtube_imports", ["owner_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_youtube_imports_owner_status", table_name="youtube_imports")
    op.drop_index("ix_youtube_imports_owner_id", table_name="youtube_imports")
    op.drop_table("youtube_imports")
