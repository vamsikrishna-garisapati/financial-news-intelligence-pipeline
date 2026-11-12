"""Normalize and validate raw Apify dataset items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.classification.service import ClassificationService
from app.services.deduplication import resolve_dedupe_keys

REQUIRED_FIELDS = ("headline", "articleLink", "source", "fetchedAt")


class ArticleValidationError(ValueError):
    """Raised when a dataset item is missing required fields or has invalid types."""


@dataclass
class CompanyRef:
    ticker: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None


@dataclass
class NormalizedArticle:
    headline: str
    source: str
    original_url: str
    canonical_url: str
    content_fingerprint: str
    fetched_at: datetime
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    image_url: str | None = None
    source_feed: str | None = None
    search_query: str | None = None
    full_text: str | None = None
    actor_event_types: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    companies: list[CompanyRef] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        # Treat as unix seconds if small enough, else milliseconds.
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    raise ArticleValidationError(f"Unsupported datetime value: {value!r}")


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ArticleValidationError(f"Expected list, got {type(value).__name__}")
    return [str(item).strip() for item in value if str(item).strip()]


def _company_refs(item: dict[str, Any], tickers: list[str]) -> list[CompanyRef]:
    refs: dict[str, CompanyRef] = {}
    details = item.get("companyDetails") or []
    if details and not isinstance(details, list):
        raise ArticleValidationError("companyDetails must be a list")

    for detail in details:
        if not isinstance(detail, dict):
            continue
        ticker = str(detail.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        refs[ticker] = CompanyRef(
            ticker=ticker,
            name=(str(detail["name"]).strip() if detail.get("name") else None),
            exchange=(str(detail["exchange"]).strip() if detail.get("exchange") else None),
            sector=(str(detail["sector"]).strip() if detail.get("sector") else None),
        )

    for ticker in tickers:
        key = ticker.upper()
        refs.setdefault(key, CompanyRef(ticker=key))

    return list(refs.values())


class ArticleProcessor:
    def __init__(self, classification: ClassificationService | None = None) -> None:
        self.classification = classification or ClassificationService()

    def normalize(self, item: dict[str, Any]) -> NormalizedArticle:
        missing = [field for field in REQUIRED_FIELDS if not item.get(field)]
        if missing:
            raise ArticleValidationError(f"Missing required fields: {', '.join(missing)}")

        headline = str(item["headline"]).strip()
        source = str(item["source"]).strip()
        original_url = str(item["articleLink"]).strip()
        fetched_at = parse_datetime(item["fetchedAt"])
        if fetched_at is None:
            raise ArticleValidationError("fetchedAt is required and must be a valid datetime")

        published_at = parse_datetime(item.get("publishedDate"))
        summary = str(item["summary"]).strip() if item.get("summary") is not None else None
        actor_event_types = _as_str_list(item.get("eventTypes"))
        tickers = [t.upper() for t in _as_str_list(item.get("tickers"))]

        canonical_url, fingerprint = resolve_dedupe_keys(
            article_link=original_url,
            dedupe_key=str(item["dedupeKey"]).strip() if item.get("dedupeKey") else None,
            headline=headline,
            source=source,
            published_at=published_at,
        )

        categories = self.classification.classify_article(
            headline=headline,
            summary=summary,
            actor_event_types=actor_event_types,
        )

        sentiment_score = item.get("sentimentScore")
        if sentiment_score is not None:
            sentiment_score = float(sentiment_score)

        return NormalizedArticle(
            headline=headline,
            source=source,
            original_url=original_url,
            canonical_url=canonical_url,
            content_fingerprint=fingerprint,
            fetched_at=fetched_at,
            author=str(item["author"]).strip() if item.get("author") else None,
            published_at=published_at,
            summary=summary,
            image_url=str(item["imageUrl"]).strip() if item.get("imageUrl") else None,
            source_feed=str(item["sourceFeed"]).strip() if item.get("sourceFeed") else None,
            search_query=str(item["searchQuery"]).strip() if item.get("searchQuery") else None,
            full_text=str(item["fullText"]) if item.get("fullText") else None,
            actor_event_types=actor_event_types,
            categories=categories,
            sentiment_score=sentiment_score,
            sentiment_label=str(item["sentimentLabel"]) if item.get("sentimentLabel") else None,
            companies=_company_refs(item, tickers),
            tickers=tickers,
            raw_payload=dict(item),
        )

    def normalize_many(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[NormalizedArticle], list[str]]:
        normalized: list[NormalizedArticle] = []
        errors: list[str] = []
        for index, item in enumerate(items):
            try:
                normalized.append(self.normalize(item))
            except (ArticleValidationError, ValueError, TypeError) as exc:
                errors.append(f"item[{index}]: {exc}")
        return normalized, errors
