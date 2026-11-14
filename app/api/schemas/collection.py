"""Collection run request/response schemas aligned with Actor inputs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import get_settings


class FeedPreset(StrEnum):
    us_markets = "us_markets"
    global_markets = "global_markets"
    earnings = "earnings"
    india_markets = "india_markets"
    crypto = "crypto"
    none = "none"
    custom = "custom"


class CollectionRunCreate(BaseModel):
    feed_preset: FeedPreset = Field(
        default=FeedPreset.us_markets,
        alias="feedPreset",
        description="Actor feedPreset",
    )
    tickers: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list, alias="searchQueries")
    search_language: str = Field(default="en", alias="searchLanguage", pattern=r"^[a-zA-Z]{2}$")
    search_country: str = Field(default="US", alias="searchCountry", pattern=r"^[a-zA-Z]{2}$")
    hours_back: int = Field(default=24, alias="hoursBack", ge=0)
    max_items: int = Field(default=50, alias="maxItems", ge=1)
    only_new_articles: bool = Field(default=False, alias="onlyNewArticles")
    enrich_articles: bool = Field(default=True, alias="enrichArticles")
    include_full_text: bool = Field(default=False, alias="includeFullText")
    include_keywords: list[str] | None = Field(default=None, alias="includeKeywords")
    exclude_keywords: list[str] = Field(default_factory=list, alias="excludeKeywords")
    use_ticker_feeds: bool = Field(default=True, alias="useTickerFeeds")
    deduplicate: bool = True

    model_config = {"populate_by_name": True}

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, value: list[str]) -> list[str]:
        return [ticker.strip().upper() for ticker in value if ticker.strip()]

    @field_validator("companies")
    @classmethod
    def normalize_companies(cls, value: list[str]) -> list[str]:
        return [company.strip() for company in value if company.strip()]

    @field_validator("search_queries")
    @classmethod
    def normalize_search_queries(cls, value: list[str]) -> list[str]:
        return [query.strip() for query in value if query.strip()]

    @model_validator(mode="after")
    def enforce_configured_limits(self) -> CollectionRunCreate:
        settings = get_settings()
        if self.max_items > settings.collection_max_items:
            raise ValueError(
                f"maxItems exceeds configured limit ({settings.collection_max_items})"
            )
        if len(self.tickers) > settings.collection_max_tickers:
            raise ValueError(
                f"tickers supports a maximum of {settings.collection_max_tickers} symbols"
            )
        if len(self.companies) > settings.collection_max_companies:
            raise ValueError(
                f"companies supports a maximum of {settings.collection_max_companies} entries"
            )
        if len(self.search_queries) > settings.collection_max_search_queries:
            raise ValueError(
                "searchQueries supports a maximum of "
                f"{settings.collection_max_search_queries} entries"
            )
        if self.hours_back > settings.collection_max_hours_back:
            raise ValueError(
                f"hoursBack exceeds configured limit ({settings.collection_max_hours_back})"
            )
        return self

    def to_actor_input(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "feedPreset": self.feed_preset.value,
            "tickers": self.tickers,
            "companies": self.companies,
            "searchQueries": self.search_queries,
            "searchLanguage": self.search_language,
            "searchCountry": self.search_country,
            "hoursBack": self.hours_back,
            "maxItems": self.max_items,
            "onlyNewArticles": self.only_new_articles,
            "enrichArticles": self.enrich_articles,
            "includeFullText": self.include_full_text,
            "excludeKeywords": self.exclude_keywords,
            "useTickerFeeds": self.use_ticker_feeds,
            "deduplicate": self.deduplicate,
        }
        if self.include_keywords is not None:
            payload["includeKeywords"] = self.include_keywords
        return payload


class CollectionRunResponse(BaseModel):
    id: uuid.UUID
    status: Literal["pending", "running", "succeeded", "failed"]
    apify_run_id: str | None = None
    apify_dataset_id: str | None = None
    actor_run_status: str | None = None
    input_payload: dict[str, Any]
    items_fetched: int
    items_inserted: int
    items_duplicated: int
    items_invalid: int
    actor_output: dict[str, Any] | None = None
    processing_errors: list[str] = Field(default_factory=list)
    error_message: str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    duration_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
