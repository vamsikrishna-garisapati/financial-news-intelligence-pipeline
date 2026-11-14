"""Analytics repository and endpoint filter tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.repositories.analytics import AnalyticsRepository
from app.db.repositories.articles import ArticleRepository
from app.services.processing import ArticleProcessor
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_articles(db_session: Session, sample_articles: list) -> None:
    processor = ArticleProcessor()
    repo = ArticleRepository(db_session)
    for item in sample_articles:
        repo.upsert_normalized(processor.normalize(item))
    db_session.commit()


def test_analytics_volume_filters_by_ticker_and_dates(
    db_session: Session,
    sample_articles: list,
) -> None:
    _seed_articles(db_session, sample_articles)
    repo = AnalyticsRepository(db_session)

    by_company = repo.news_volume(group_by="company", ticker="AAPL")
    assert by_company
    assert all(row["ticker"] == "AAPL" for row in by_company)

    by_source = repo.news_volume(
        group_by="source",
        ticker="AAPL",
        published_after=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert by_source
    assert all("count" in row and "source" in row for row in by_source)

    by_date = repo.news_volume(
        group_by="date",
        published_before=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert by_date
    assert all(row["date"] is not None for row in by_date)


def test_analytics_categories_respect_date_window(
    db_session: Session,
    sample_articles: list,
) -> None:
    _seed_articles(db_session, sample_articles)
    repo = AnalyticsRepository(db_session)
    items = repo.categories(
        published_after=datetime(2020, 1, 1, tzinfo=UTC),
        published_before=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert items
    assert all("category" in row and "count" in row for row in items)


def test_analytics_api_ticker_filter(client: TestClient, sample_articles: list) -> None:
    # Seed via collection flow already available through client fixture mock.
    client.post(
        "/collection-runs",
        json={"feedPreset": "us_markets", "maxItems": 5, "includeKeywords": []},
    )
    response = client.get(
        "/analytics/news-volume",
        params={"group_by": "company", "ticker": "AAPL"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["group_by"] == "company"
    assert all(item["ticker"] == "AAPL" for item in payload["items"])
