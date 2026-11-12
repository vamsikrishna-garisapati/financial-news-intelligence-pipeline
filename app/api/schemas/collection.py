"""Collection run request/response schemas aligned with Actor inputs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
    search_queries: list[str] = Field(default_factory=list, alias="searchQueries", max_length=10)
    search_language: str = Field(default="en", alias="searchLanguage", pattern=r"^[a-zA-Z]{2}$")
    search_country: str = Field(default="US", alias="searchCountry", pattern=r"^[a-zA-Z]{2}$")
    hours_back: int = Field(default=24, alias="hoursBack", ge=0, le=720)
    max_items: int = Field(default=50, alias="maxItems", ge=1, le=500)
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
        if len(value) > 20:
            raise ValueError("tickers supports a maximum of 20 symbols")
        return [ticker.strip().upper() for ticker in value if ticker.strip()]

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
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
