"""initial schema

Revision ID: 20260326_0001
Revises:
Create Date: 2026-03-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260326_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    collection_run_status = postgresql.ENUM(
        "pending",
        "running",
        "succeeded",
        "failed",
        name="collection_run_status",
        create_type=False,
    )
    collection_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"], unique=False)

    op.create_table(
        "articles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("source_feed", sa.Text(), nullable=True),
        sa.Column("search_query", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("actor_event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("sentiment_label", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_url"),
        sa.UniqueConstraint("content_fingerprint"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"], unique=False)
    op.create_index("ix_articles_source", "articles", ["source"], unique=False)
    op.create_index(
        "ix_articles_categories",
        "articles",
        ["categories"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "running",
                "succeeded",
                "failed",
                name="collection_run_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("apify_run_id", sa.String(length=64), nullable=True),
        sa.Column("apify_dataset_id", sa.String(length=64), nullable=True),
        sa.Column("actor_run_status", sa.String(length=64), nullable=True),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("items_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_duplicated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_invalid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_runs_status", "collection_runs", ["status"], unique=False)
    op.create_index("ix_collection_runs_apify_run_id", "collection_runs", ["apify_run_id"], unique=False)

    op.create_table(
        "article_companies",
        sa.Column("article_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id", "company_id"),
        sa.UniqueConstraint("article_id", "company_id", name="uq_article_company"),
    )

    op.create_table(
        "collection_run_articles",
        sa.Column("collection_run_id", sa.UUID(), nullable=False),
        sa.Column("article_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_run_id"], ["collection_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("collection_run_id", "article_id"),
        sa.UniqueConstraint("collection_run_id", "article_id", name="uq_collection_run_article"),
    )


def downgrade() -> None:
    op.drop_table("collection_run_articles")
    op.drop_table("article_companies")
    op.drop_index("ix_collection_runs_apify_run_id", table_name="collection_runs")
    op.drop_index("ix_collection_runs_status", table_name="collection_runs")
    op.drop_table("collection_runs")
    op.drop_index("ix_articles_categories", table_name="articles")
    op.drop_index("ix_articles_source", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_table("articles")
    op.drop_index("ix_companies_ticker", table_name="companies")
    op.drop_table("companies")
    op.execute("DROP TYPE IF EXISTS collection_run_status")
