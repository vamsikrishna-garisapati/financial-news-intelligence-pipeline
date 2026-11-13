"""Apify Actor client wrapper with retries, start/wait split, and timeouts."""

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
class ActorRunHandle:
    run_id: str
    dataset_id: str | None
    key_value_store_id: str | None
    status: str


@dataclass(frozen=True)
class ActorRunResult:
    run_id: str
    dataset_id: str | None
    key_value_store_id: str | None
    status: str
    items: list[dict[str, Any]]
    actor_run_status: str | None


def _run_field(run: Any, *names: str) -> Any:
    """Read a field from a Run model, mapping, or object with either snake/camel case."""
    if run is None:
        return None
    if isinstance(run, dict):
        for name in names:
            if name in run and run[name] is not None:
                return run[name]
        return None
    for name in names:
        if hasattr(run, name):
            value = getattr(run, name)
            if value is not None:
                return value
    return None


def handle_from_run(run: Any) -> ActorRunHandle:
    run_id = str(_run_field(run, "id") or "")
    if not run_id:
        raise ApifyIntegrationError("Apify run response missing id")
    dataset_id = _run_field(run, "default_dataset_id", "defaultDatasetId")
    kv_store_id = _run_field(run, "default_key_value_store_id", "defaultKeyValueStoreId")
    status = str(_run_field(run, "status") or "UNKNOWN")
    return ActorRunHandle(
        run_id=run_id,
        dataset_id=str(dataset_id) if dataset_id else None,
        key_value_store_id=str(kv_store_id) if kv_store_id else None,
        status=status,
    )


class ApifyNewsClient:
    """Thin wrapper around ApifyClient for the stock-market-news-collector Actor."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.apify_token:
            raise ApifyIntegrationError(
                "APIFY_TOKEN is not configured. Set it in the environment or .env file."
            )
        self._client = ApifyClient(token=self.settings.apify_token)

    def start_run(self, run_input: dict[str, Any]) -> ActorRunHandle:
        """Start the Actor and return immediately with the Apify run id."""

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
            return self._client.actor(self.settings.apify_actor_id).start(
                run_input=run_input,
                run_timeout=timedelta(seconds=self.settings.apify_timeout_secs),
            )

        try:
            run = _call()
        except ApifyApiError as exc:
            raise ApifyIntegrationError(f"Apify API error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ApifyIntegrationError(f"Apify Actor start failed: {exc}") from exc

        if run is None:
            raise ApifyIntegrationError("Apify Actor start returned no run data")
        return handle_from_run(run)

    def wait_for_run(self, run_id: str) -> ActorRunHandle:
        """Wait for an existing Apify run to finish (does not start a new run)."""

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.apify_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((ApifyApiError, TimeoutError, ConnectionError)),
        )
        def _call() -> Any:
            logger.info("Waiting for Apify run %s", run_id)
            return self._client.run(run_id).wait_for_finish(
                wait_duration=timedelta(seconds=self.settings.apify_timeout_secs),
            )

        try:
            run = _call()
        except ApifyApiError as exc:
            raise ApifyIntegrationError(f"Apify API error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ApifyIntegrationError(f"Apify Actor wait failed: {exc}") from exc

        if run is None:
            # Timed out waiting — fetch current status for diagnostics.
            current = self._client.run(run_id).get()
            if current is None:
                raise ApifyIntegrationError(f"Apify run {run_id} not found while waiting")
            handle = handle_from_run(current)
            raise ApifyIntegrationError(
                f"Apify run {run_id} did not finish within timeout (status={handle.status})"
            )
        return handle_from_run(run)

    def fetch_run_result(self, handle: ActorRunHandle) -> ActorRunResult:
        """Fetch dataset items and OUTPUT runStatus for a finished (or known) run."""
        items: list[dict[str, Any]] = []
        dataset_id = handle.dataset_id
        kv_store_id = handle.key_value_store_id

        if not dataset_id or not kv_store_id:
            current = self._client.run(handle.run_id).get()
            if current is not None:
                refreshed = handle_from_run(current)
                dataset_id = dataset_id or refreshed.dataset_id
                kv_store_id = kv_store_id or refreshed.key_value_store_id
                handle = ActorRunHandle(
                    run_id=handle.run_id,
                    dataset_id=dataset_id,
                    key_value_store_id=kv_store_id,
                    status=refreshed.status or handle.status,
                )

        if dataset_id:
            items = list(self._client.dataset(dataset_id).iterate_items())

        actor_run_status = self._read_actor_run_status(kv_store_id)
        return ActorRunResult(
            run_id=handle.run_id,
            dataset_id=dataset_id,
            key_value_store_id=kv_store_id,
            status=handle.status,
            items=items,
            actor_run_status=actor_run_status,
        )

    def run_actor(self, run_input: dict[str, Any]) -> ActorRunResult:
        """Start, wait, and fetch — convenience for tests and simple callers."""
        started = self.start_run(run_input)
        finished = self.wait_for_run(started.run_id)
        return self.fetch_run_result(finished)

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
        value = record.get("value") if isinstance(record, dict) else getattr(record, "value", None)
        if isinstance(value, dict):
            status = value.get("runStatus")
            return str(status) if status is not None else None
        return None
