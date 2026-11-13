"""Normalize and validate raw Apify dataset items."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.classification.service import ClassificationService
from app.services.deduplication import resolve_dedupe_keys

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("headline", "articleLink", "source", "fetchedAt")

# Uppercase ticker symbols: letters first, then alnum / . / - up to 16 chars total.
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


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
    classification_method: str = "rules"
    sentiment_score: float | None = None
    sentiment_label: str | None = None
    companies: list[CompanyRef] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    processing_error: str | None = None
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


def is_valid_ticker(ticker: str) -> bool:
    return bool(TICKER_PATTERN.fullmatch(ticker))


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ArticleValidationError(f"Expected list, got {type(value).__name__}")
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_tickers(raw_tickers: list[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw in raw_tickers:
        ticker = raw.upper()
        if not is_valid_ticker(ticker):
            warnings.append(f"invalid ticker skipped: {raw!r}")
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        valid.append(ticker)
    return valid, warnings


def _company_refs(
    item: dict[str, Any],
    tickers: list[str],
) -> tuple[list[CompanyRef], list[str]]:
    refs: dict[str, CompanyRef] = {}
    warnings: list[str] = []
    details = item.get("companyDetails") or []
    if details and not isinstance(details, list):
        raise ArticleValidationError("companyDetails must be a list")

    for detail in details:
        if not isinstance(detail, dict):
            continue
        ticker = str(detail.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if not is_valid_ticker(ticker):
            warnings.append(f"invalid companyDetails ticker skipped: {ticker!r}")
            continue
        name = str(detail["name"]).strip() if detail.get("name") else None
        exchange = str(detail["exchange"]).strip() if detail.get("exchange") else None
        sector = str(detail["sector"]).strip() if detail.get("sector") else None
        existing = refs.get(ticker)
        if existing is not None:
            if name and existing.name and name != existing.name:
                warnings.append(
                    f"companyDetails name conflict for {ticker}: "
                    f"{existing.name!r} vs {name!r}"
                )
            # Keep first non-empty metadata; fill blanks only.
            refs[ticker] = CompanyRef(
                ticker=ticker,
                name=existing.name or name,
                exchange=existing.exchange or exchange,
                sector=existing.sector or sector,
            )
            continue
        refs[ticker] = CompanyRef(
            ticker=ticker,
            name=name,
            exchange=exchange,
            sector=sector,
        )

    for ticker in tickers:
        refs.setdefault(ticker, CompanyRef(ticker=ticker))

    # Drop company refs whose ticker was never validated into tickers list and is invalid
    # (already filtered). Keep ticker-only refs for valid tickers.
    return list(refs.values()), warnings


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
        tickers, ticker_warnings = _validate_tickers(_as_str_list(item.get("tickers")))
        companies, company_warnings = _company_refs(item, tickers)
        processing_warnings = [*ticker_warnings, *company_warnings]
        if processing_warnings:
            logger.warning(
                "Article processing warnings for %r: %s",
                headline[:80],
                processing_warnings,
            )

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
            classification_method=self.classification.method,
            sentiment_score=sentiment_score,
            sentiment_label=str(item["sentimentLabel"]) if item.get("sentimentLabel") else None,
            companies=companies,
            tickers=tickers,
            processing_error="; ".join(processing_warnings) if processing_warnings else None,
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
