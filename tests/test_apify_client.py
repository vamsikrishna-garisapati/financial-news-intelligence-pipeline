"""Apify client wrapper tests with mocks."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from apify_client.errors import ApifyApiError
from app.config import Settings
from app.integrations.apify import ApifyIntegrationError, ApifyNewsClient


def test_missing_token_raises() -> None:
    settings = Settings(apify_token=None)
    with pytest.raises(ApifyIntegrationError, match="APIFY_TOKEN"):
        ApifyNewsClient(settings=settings)


def test_run_actor_success(sample_articles: list[dict[str, Any]]) -> None:
    settings = Settings(apify_token="test-token", apify_max_retries=1)
    with patch("app.integrations.apify.ApifyClient") as client_cls:
        client = client_cls.return_value
        actor = client.actor.return_value
        actor.call.return_value = {
            "id": "run-1",
            "defaultDatasetId": "ds-1",
            "defaultKeyValueStoreId": "kv-1",
            "status": "SUCCEEDED",
        }
        client.dataset.return_value.iterate_items.return_value = iter(sample_articles)
        client.key_value_store.return_value.get_record.return_value = {
            "value": {"runStatus": "ok", "count": len(sample_articles)}
        }

        result = ApifyNewsClient(settings=settings).run_actor({"feedPreset": "us_markets"})

    assert result.run_id == "run-1"
    assert result.dataset_id == "ds-1"
    assert result.actor_run_status == "ok"
    assert len(result.items) == 3


def test_run_actor_retries_then_fails() -> None:
    settings = Settings(apify_token="test-token", apify_max_retries=2)
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"
    response.headers = {}
    with patch("app.integrations.apify.ApifyClient") as client_cls:
        client = client_cls.return_value
        actor = client.actor.return_value
        actor.call.side_effect = ApifyApiError(response, attempt=1)
        with pytest.raises(ApifyIntegrationError):
            ApifyNewsClient(settings=settings).run_actor({"maxItems": 1})
