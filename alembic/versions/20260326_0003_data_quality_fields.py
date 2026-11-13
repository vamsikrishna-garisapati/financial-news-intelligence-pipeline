"""data quality fields for articles and collection runs

Revision ID: 20260326_0003
Revises: 20260326_0002
Create Date: 2026-03-26 00:02:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260326_0003"
down_revision: str | Sequence[str] | None = "20260326_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "classification_method",
            sa.String(length=64),
            server_default="rules",
            nullable=False,
        ),
    )
    op.add_column(
        "articles",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column("actor_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "collection_runs",
        sa.Column(
            "processing_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("collection_runs", "processing_errors")
    op.drop_column("collection_runs", "actor_output")
    op.drop_column("articles", "processing_error")
    op.drop_column("articles", "classification_method")
