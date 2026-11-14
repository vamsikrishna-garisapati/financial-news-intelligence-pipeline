"""Data quality: URL canonicalization, tickers, timestamps, classification provenance."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.db.models import CollectionRunStatus
from app.db.repositories.articles import ArticleRepository
from app.integrations.apify import ActorRunHandle, ActorRunResult
from app.services.collection import CollectionService
from app.services.deduplication import canonicalize_url
from app.services.processing import ArticleProcessor
from sqlalchemy.orm import Session


def test_canonicalize_sorts_query_params_and_drops_default_ports() -> None:
    url = "https://example.com:443/path?b=2&a=1"
    assert canonicalize_url(url) == "https://example.com/path?a=1&b=2"

    http_url = "http://example.com:80/news"
    assert canonicalize_url(http_url) == "http://example.com/news"


def test_canonicalize_strips_www_prefix() -> None:
    assert (
        canonicalize_url("https://www.example.com/story?id=1")
        == "https://example.com/story?id=1"
    )
    # Non-www subdomains are preserved
    assert (
        canonicalize_url("https://news.example.com/story")
        == "https://news.example.com/story"
    )


def test_normalize_skips_invalid_tickers_and_records_warning(
    sample_articles: list[dict[str, Any]],
) -> None:
    item = dict(sample_articles[1])
    item["tickers"] = ["AAPL", "BAD TICKER!!!", "nvda"]
    item["companyDetails"] = [
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "sector": "Technology"},
        {"ticker": "???", "name": "Bad"},
    ]

    article = ArticleProcessor().normalize(item)

    assert article.tickers == ["AAPL", "NVDA"]
    assert {c.ticker for c in article.companies} == {"AAPL", "NVDA"}
    assert article.classification_method == "rules"
    assert article.processing_error is not None
    message = article.processing_error.lower()
    assert "bad ticker" in message or "invalid ticker" in message


def test_normalize_missing_published_at_still_works(
    sample_articles: list[dict[str, Any]],
) -> None:
    item = dict(sample_articles[0])
    item.pop("publishedDate", None)
    article = ArticleProcessor().normalize(item)
    assert article.published_at is None
    assert article.fetched_at is not None
    assert article.content_fingerprint


def test_company_detail_name_conflict_logged(
    sample_articles: list[dict[str, Any]],
) -> None:
    item = dict(sample_articles[1])
    item["tickers"] = ["AAPL"]
    item["companyDetails"] = [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "AAPL", "name": "Different Name Co"},
    ]
    article = ArticleProcessor().normalize(item)
    assert article.companies[0].ticker == "AAPL"
    assert article.companies[0].name == "Apple Inc."
    assert article.processing_error is not None
    assert "conflict" in article.processing_error.lower()


def test_article_persists_classification_method(
    db_session: Session,
    sample_articles: list[dict[str, Any]],
) -> None:
    article = ArticleProcessor().normalize(sample_articles[1])
    repo = ArticleRepository(db_session)
    saved, inserted = repo.upsert_normalized(article)
    db_session.commit()

    assert inserted is True
    assert saved.classification_method == "rules"
    assert saved.processing_error is None


def test_collection_stores_actor_output_and_processing_errors(
    db_session: Session,
    sample_articles: list[dict[str, Any]],
) -> None:
    mock_client = MagicMock()
    handle = ActorRunHandle(
        run_id="apify-run-dq",
        dataset_id="dataset-dq",
        key_value_store_id="kv-dq",
        status="SUCCEEDED",
    )
    mock_client.start_run.return_value = handle
    mock_client.wait_for_run.return_value = handle
    mock_client.fetch_run_result.return_value = ActorRunResult(
        run_id="apify-run-dq",
        dataset_id="dataset-dq",
        key_value_store_id="kv-dq",
        status="SUCCEEDED",
        items=[*sample_articles, {"headline": "broken"}],
        actor_run_status="ok",
        actor_output={"runStatus": "ok", "count": 3, "sources": ["rss"]},
    )

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    claimed = service.runs.claim_next(lock_owner="dq-test", max_attempts=3)
    assert claimed is not None
    service.execute_claimed_run(claimed.id)

    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded
    assert finished.actor_output == {"runStatus": "ok", "count": 3, "sources": ["rss"]}
    assert finished.processing_errors
    assert any("item[" in err for err in finished.processing_errors)
    assert finished.items_invalid >= 1
