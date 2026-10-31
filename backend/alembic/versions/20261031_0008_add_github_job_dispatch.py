"""Add recoverable GitHub Actions dispatch metadata.

Revision ID: 20261031_0008
Revises: 20261031_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20261031_0008"
down_revision = "20261031_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("dispatch_status", sa.String(32)))
    op.add_column(
        "processing_jobs",
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("processing_jobs", sa.Column("dispatch_error_message", sa.Text()))
    op.add_column(
        "processing_jobs", sa.Column("dispatch_requested_at", sa.DateTime(timezone=True))
    )
    op.add_column("processing_jobs", sa.Column("dispatched_at", sa.DateTime(timezone=True)))
    if op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_processing_jobs_dispatch_attempts_nonnegative",
            "processing_jobs",
            "dispatch_attempts >= 0",
        )
    op.create_index(
        "ix_processing_jobs_dispatch",
        "processing_jobs",
        ["dispatch_status", "dispatched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_dispatch", table_name="processing_jobs")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "ck_processing_jobs_dispatch_attempts_nonnegative",
            "processing_jobs",
            type_="check",
        )
    op.drop_column("processing_jobs", "dispatched_at")
    op.drop_column("processing_jobs", "dispatch_requested_at")
    op.drop_column("processing_jobs", "dispatch_error_message")
    op.drop_column("processing_jobs", "dispatch_attempts")
    op.drop_column("processing_jobs", "dispatch_status")
