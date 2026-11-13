"""News and company response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CompanySummary(BaseModel):
    ticker: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None

    model_config = {"from_attributes": True}


class ArticleSummary(BaseModel):
    id: uuid.UUID
    headline: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None
    original_url: str
    categories: list[str] = Field(default_factory=list)
    companies: list[CompanySummary] = Field(default_factory=list)
    sentiment_label: str | None = Field(
        default=None,
        description="Best-effort Actor label only; not a verified financial signal.",
    )

    model_config = {"from_attributes": True}


class ArticleDetail(ArticleSummary):
    author: str | None = None
    image_url: str | None = None
    canonical_url: str
    source_feed: str | None = None
    search_query: str | None = None
    fetched_at: datetime
    full_text: str | None = None
    actor_event_types: list[str] = Field(default_factory=list)
    classification_method: str = "rules"
    processing_error: str | None = None
    sentiment_score: float | None = Field(
        default=None,
        description="Best-effort Actor score only; not investment advice.",
    )
    created_at: datetime
