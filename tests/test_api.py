"""API endpoint tests with mocked Apify."""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

from app.api.deps import get_session
from app.api.routes.collection_runs import get_collection_scheduler
from app.integrations.apify import ApifyIntegrationError
from app.main import create_app
from app.services.collection import CollectionService
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_collection_run_and_news_flow(client: TestClient) -> None:
    create = client.post(
        "/collection-runs",
        json={
            "feedPreset": "us_markets",
            "maxItems": 5,
            "includeKeywords": [],
            "tickers": ["AAPL", "NVDA"],
        },
    )
    assert create.status_code == 202
    body = create.json()
    run_id = body["id"]
    assert body["status"] in {"pending", "running", "succeeded"}

    status_body = None
    for _ in range(10):
        status = client.get(f"/collection-runs/{run_id}")
        assert status.status_code == 200
        status_body = status.json()
        if status_body["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)

    assert status_body is not None
    assert status_body["status"] == "succeeded"
    assert status_body["items_fetched"] == 3
    assert status_body["items_inserted"] == 3

    news = client.get("/news", params={"limit": 10})
    assert news.status_code == 200
    payload = news.json()
    assert payload["pagination"]["total"] == 3
    assert len(payload["items"]) == 3

    article_id = payload["items"][0]["id"]
    detail = client.get(f"/news/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["original_url"]

    company_news = client.get("/companies/AAPL/news")
    assert company_news.status_code == 200
    assert company_news.json()["pagination"]["total"] >= 1

    volume = client.get("/analytics/news-volume", params={"group_by": "company"})
    assert volume.status_code == 200
    assert any(item["ticker"] == "AAPL" for item in volume.json()["items"])

    categories = client.get("/analytics/categories")
    assert categories.status_code == 200
    assert categories.json()["items"]


def test_get_unknown_article_404(client: TestClient) -> None:
    response = client.get(f"/news/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Article not found"


def test_get_unknown_company_404(client: TestClient) -> None:
    response = client.get("/companies/ZZZZ/news")
    assert response.status_code == 404


def test_collection_run_not_found(client: TestClient) -> None:
    response = client.get(f"/collection-runs/{uuid.uuid4()}")
    assert response.status_code == 404


def test_validation_error_on_bad_input(client: TestClient) -> None:
    response = client.post("/collection-runs", json={"maxItems": 0})
    assert response.status_code == 422


def test_collection_run_apify_failure(db_session: Session) -> None:
    failing = MagicMock()
    failing.run_actor.side_effect = ApifyIntegrationError("boom")

    app = create_app()

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    def _inline_scheduler(run_id: uuid.UUID, _background_tasks: BackgroundTasks) -> None:
        CollectionService(db_session, apify_client=failing).execute_run(run_id)

    app.dependency_overrides[get_session] = _override_db
    app.dependency_overrides[get_collection_scheduler] = lambda: _inline_scheduler

    with TestClient(app) as client:
        create = client.post("/collection-runs", json={"feedPreset": "us_markets", "maxItems": 1})
        run_id = create.json()["id"]
        status = client.get(f"/collection-runs/{run_id}")
        assert status.json()["status"] == "failed"
        assert "boom" in status.json()["error_message"]

    app.dependency_overrides.clear()


def test_news_filters(client: TestClient) -> None:
    client.post(
        "/collection-runs",
        json={"feedPreset": "us_markets", "maxItems": 5, "includeKeywords": []},
    )
    filtered = client.get("/news", params={"ticker": "NVDA", "category": "market_updates"})
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] >= 1

    source_volume = client.get("/analytics/news-volume", params={"group_by": "source"})
    assert source_volume.status_code == 200
    assert source_volume.json()["items"]

    date_volume = client.get("/analytics/news-volume", params={"group_by": "date"})
    assert date_volume.status_code == 200
