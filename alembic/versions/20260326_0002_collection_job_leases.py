"""collection job lease and retry columns

Revision ID: 20260326_0002
Revises: 20260326_0001
Create Date: 2026-03-26 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260326_0002"
down_revision: str | Sequence[str] | None = "20260326_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collection_runs",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "collection_runs",
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "collection_runs",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column("lock_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_collection_runs_next_attempt_at",
        "collection_runs",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_collection_runs_heartbeat_at",
        "collection_runs",
        ["heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_collection_runs_heartbeat_at", table_name="collection_runs")
    op.drop_index("ix_collection_runs_next_attempt_at", table_name="collection_runs")
    op.drop_column("collection_runs", "duration_ms")
    op.drop_column("collection_runs", "next_attempt_at")
    op.drop_column("collection_runs", "lock_owner")
    op.drop_column("collection_runs", "heartbeat_at")
    op.drop_column("collection_runs", "locked_at")
    op.drop_column("collection_runs", "max_attempts")
    op.drop_column("collection_runs", "attempt_count")
