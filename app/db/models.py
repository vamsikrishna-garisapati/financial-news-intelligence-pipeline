"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CollectionRunStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    articles: Mapped[list[Article]] = relationship(
        "Article",
        secondary="article_companies",
        back_populates="companies",
    )


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_source", "source"),
        Index("ix_articles_categories", "categories", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_feed: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_event_types: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    categories: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    classification_method: Mapped[str] = mapped_column(String(64), nullable=False, default="rules")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    companies: Mapped[list[Company]] = relationship(
        "Company",
        secondary="article_companies",
        back_populates="articles",
    )
    collection_runs: Mapped[list[CollectionRun]] = relationship(
        "CollectionRun",
        secondary="collection_run_articles",
        back_populates="articles",
    )


class ArticleCompany(Base):
    __tablename__ = "article_companies"
    __table_args__ = (UniqueConstraint("article_id", "company_id", name="uq_article_company"),)

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[CollectionRunStatus] = mapped_column(
        Enum(CollectionRunStatus, name="collection_run_status", native_enum=True),
        nullable=False,
        default=CollectionRunStatus.pending,
        index=True,
    )
    apify_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    apify_dataset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_run_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    items_fetched: Mapped[int] = mapped_column(nullable=False, default=0)
    items_inserted: Mapped[int] = mapped_column(nullable=False, default=0)
    items_duplicated: Mapped[int] = mapped_column(nullable=False, default=0)
    items_invalid: Mapped[int] = mapped_column(nullable=False, default=0)
    actor_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    processing_errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    articles: Mapped[list[Article]] = relationship(
        "Article",
        secondary="collection_run_articles",
        back_populates="collection_runs",
    )


class CollectionRunArticle(Base):
    __tablename__ = "collection_run_articles"
    __table_args__ = (
        UniqueConstraint("collection_run_id", "article_id", name="uq_collection_run_article"),
    )

    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collection_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
