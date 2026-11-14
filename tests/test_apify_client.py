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


def test_start_wait_fetch_success(sample_articles: list[dict[str, Any]]) -> None:
    settings = Settings(apify_token="test-token", apify_max_retries=1)
    with patch("app.integrations.apify.ApifyClient") as client_cls:
        client = client_cls.return_value
        actor = client.actor.return_value
        actor.start.return_value = {
            "id": "run-1",
            "defaultDatasetId": "ds-1",
            "defaultKeyValueStoreId": "kv-1",
            "status": "RUNNING",
        }
        run_client = client.run.return_value
        run_client.wait_for_finish.return_value = {
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

    actor.start.assert_called_once()
    run_client.wait_for_finish.assert_called_once()
    assert result.run_id == "run-1"
    assert result.dataset_id == "ds-1"
    assert result.actor_run_status == "ok"
    assert len(result.items) == 3


def test_wait_for_run_does_not_start_actor() -> None:
    settings = Settings(apify_token="test-token", apify_max_retries=1)
    with patch("app.integrations.apify.ApifyClient") as client_cls:
        client = client_cls.return_value
        run_client = client.run.return_value
        run_client.wait_for_finish.return_value = {
            "id": "existing-run",
            "default_dataset_id": "ds-2",
            "default_key_value_store_id": "kv-2",
            "status": "SUCCEEDED",
        }

        handle = ApifyNewsClient(settings=settings).wait_for_run("existing-run")

    client.actor.assert_not_called()
    client.run.assert_called_with("existing-run")
    assert handle.run_id == "existing-run"
    assert handle.dataset_id == "ds-2"


def test_start_run_retries_then_fails() -> None:
    settings = Settings(apify_token="test-token", apify_max_retries=2)
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"
    response.headers = {}
    with patch("app.integrations.apify.ApifyClient") as client_cls:
        client = client_cls.return_value
        actor = client.actor.return_value
        actor.start.side_effect = ApifyApiError(response, attempt=1)
        with pytest.raises(ApifyIntegrationError):
            ApifyNewsClient(settings=settings).start_run({"maxItems": 1})
