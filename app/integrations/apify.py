"""Apify Actor client wrapper with retries and timeouts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ApifyIntegrationError(Exception):
    """Raised when Apify calls fail after retries or configuration is missing."""


@dataclass(frozen=True)
class ActorRunResult:
    run_id: str
    dataset_id: str | None
    key_value_store_id: str | None
    status: str
    items: list[dict[str, Any]]
    actor_run_status: str | None


class ApifyNewsClient:
    """Thin wrapper around ApifyClient for the stock-market-news-collector Actor."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.apify_token:
            raise ApifyIntegrationError(
                "APIFY_TOKEN is not configured. Set it in the environment or .env file."
            )
        self._client = ApifyClient(token=self.settings.apify_token)

    def run_actor(self, run_input: dict[str, Any]) -> ActorRunResult:
        """Start the Actor, wait for completion, and return dataset items."""

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.apify_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((ApifyApiError, TimeoutError, ConnectionError)),
        )
        def _call() -> Any:
            logger.info(
                "Starting Apify Actor %s with timeout=%ss",
                self.settings.apify_actor_id,
                self.settings.apify_timeout_secs,
            )
            run = self._client.actor(self.settings.apify_actor_id).call(
                run_input=run_input,
                run_timeout=timedelta(seconds=self.settings.apify_timeout_secs),
            )
            if run is None:
                raise ApifyIntegrationError("Apify Actor call returned no run data")
            return run

        try:
            run = _call()
        except ApifyApiError as exc:
            raise ApifyIntegrationError(f"Apify API error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ApifyIntegrationError(f"Apify Actor run failed: {exc}") from exc

        run_data = run if isinstance(run, dict) else dict(run)
        run_id = str(run_data.get("id") or "")
        dataset_id = run_data.get("defaultDatasetId")
        kv_store_id = run_data.get("defaultKeyValueStoreId")
        status = str(run_data.get("status") or "UNKNOWN")

        items: list[dict[str, Any]] = []
        if dataset_id:
            items = list(self._client.dataset(dataset_id).iterate_items())

        actor_run_status = self._read_actor_run_status(kv_store_id)

        return ActorRunResult(
            run_id=run_id,
            dataset_id=dataset_id,
            key_value_store_id=kv_store_id,
            status=status,
            items=items,
            actor_run_status=actor_run_status,
        )

    def _read_actor_run_status(self, kv_store_id: str | None) -> str | None:
        if not kv_store_id:
            return None
        try:
            record = self._client.key_value_store(kv_store_id).get_record("OUTPUT")
        except ApifyApiError:
            logger.warning("Unable to read OUTPUT record from key-value store %s", kv_store_id)
            return None
        if not record:
            return None
        value = record.get("value")
        if isinstance(value, dict):
            status = value.get("runStatus")
            return str(status) if status is not None else None
        return None
