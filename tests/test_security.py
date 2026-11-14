"""Security hardening tests: CORS, collection limits, secret redaction."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator

import pytest
from app.api.deps import get_session
from app.api.routes.collection_runs import get_collection_notifier
from app.api.schemas.collection import CollectionRunCreate
from app.config import Settings, get_settings
from app.main import create_app
from app.security.redact import RedactingFilter, redact_secrets
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session


@pytest.fixture
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_redact_secrets_masks_token_values() -> None:
    text = "Using token secret-token-value in request"
    redacted = redact_secrets(text, ["secret-token-value"])
    assert "secret-token-value" not in redacted
    assert "***" in redacted


def test_redacting_filter_masks_apify_token_in_logs(clear_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "super-secret-apify-token")
    monkeypatch.setenv("JOB_WORKER_ENABLED", "false")
    get_settings.cache_clear()

    logger = logging.getLogger("test.redact")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Capture()
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    try:
        logger.info("APIFY_TOKEN=super-secret-apify-token should stay hidden")
        assert records
        assert "super-secret-apify-token" not in records[0]
    finally:
        logger.removeHandler(handler)


def test_cors_allows_configured_origin(clear_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("JOB_WORKER_ENABLED", "false")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unknown_origin(clear_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("JOB_WORKER_ENABLED", "false")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_collection_limits_from_settings(clear_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("COLLECTION_MAX_ITEMS", "10")
    monkeypatch.setenv("COLLECTION_MAX_TICKERS", "2")
    monkeypatch.setenv("COLLECTION_MAX_HOURS_BACK", "48")
    monkeypatch.setenv("COLLECTION_MAX_SEARCH_QUERIES", "3")
    monkeypatch.setenv("COLLECTION_MAX_COMPANIES", "5")
    get_settings.cache_clear()

    with pytest.raises(ValidationError, match="maxItems"):
        CollectionRunCreate.model_validate({"maxItems": 11})

    with pytest.raises(ValidationError, match="tickers"):
        CollectionRunCreate.model_validate({"tickers": ["AAPL", "MSFT", "NVDA"]})

    with pytest.raises(ValidationError, match="hoursBack"):
        CollectionRunCreate.model_validate({"hoursBack": 100})

    ok = CollectionRunCreate.model_validate(
        {"maxItems": 10, "tickers": ["AAPL", "MSFT"], "hoursBack": 48}
    )
    assert ok.max_items == 10


def test_api_returns_422_when_collection_over_limit(
    db_session: Session,
    clear_settings_cache,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JOB_WORKER_ENABLED", "false")
    monkeypatch.setenv("COLLECTION_MAX_ITEMS", "5")
    get_settings.cache_clear()

    app = create_app()

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    def _noop(_run_id: uuid.UUID) -> None:
        return None

    app.dependency_overrides[get_session] = _override_db
    app.dependency_overrides[get_collection_notifier] = lambda: _noop

    with TestClient(app) as client:
        response = client.post("/collection-runs", json={"maxItems": 6})

    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_settings_parse_cors_origins() -> None:
    settings = Settings(cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_production_cors_drops_wildcard() -> None:
    settings = Settings(app_env="production", cors_origins="*,http://localhost:3000")
    assert "*" not in settings.cors_origin_list
    assert "http://localhost:3000" in settings.cors_origin_list
