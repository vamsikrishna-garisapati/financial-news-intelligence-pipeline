"""Structured logging and collection event observability tests."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock

from app.db.models import CollectionRunStatus
from app.integrations.apify import ActorRunHandle, ActorRunResult
from app.observability.logging import JsonFormatter, configure_logging, log_event
from app.services.collection import CollectionService
from sqlalchemy.orm import Session


def test_json_formatter_emits_event_fields() -> None:
    record = logging.LogRecord(
        name="test.obs",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="collection finished",
        args=(),
        exc_info=None,
    )
    record.event = "collection.succeeded"
    record.run_id = "abc-123"
    record.items_fetched = 3
    record.duration_ms = 42

    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "collection.succeeded"
    assert payload["run_id"] == "abc-123"
    assert payload["items_fetched"] == 3
    assert payload["duration_ms"] == 42
    assert payload["message"] == "collection finished"
    assert payload["level"] == "INFO"


def test_configure_logging_json_and_redacts_token(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_TOKEN", "obs-secret-token")
    from app.config import get_settings

    get_settings.cache_clear()
    previous_handlers = list(logging.getLogger().handlers)

    stream = StringIO()
    configure_logging("INFO", log_format="json", stream=stream)

    try:
        logging.getLogger("test.obs.redact").info("token=obs-secret-token should hide")
        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        assert lines
        assert "obs-secret-token" not in lines[-1]
        payload = json.loads(lines[-1])
        assert payload["level"] == "INFO"
    finally:
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in previous_handlers:
            root.addHandler(handler)
        get_settings.cache_clear()


def test_log_event_attaches_structured_fields() -> None:
    stream = StringIO()
    configure_logging("INFO", log_format="json", stream=stream)
    logger = logging.getLogger("test.obs.event")
    log_event(
        logger,
        logging.INFO,
        event="job.claimed",
        message="claimed run",
        run_id="run-1",
        attempt_count=2,
    )
    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert payload["event"] == "job.claimed"
    assert payload["run_id"] == "run-1"
    assert payload["attempt_count"] == 2


def test_collection_success_emits_structured_counters(
    db_session: Session,
    sample_articles: list,
    caplog,
) -> None:
    mock_client = MagicMock()
    handle = ActorRunHandle(
        run_id="apify-obs-1",
        dataset_id="dataset-obs",
        key_value_store_id="kv-obs",
        status="SUCCEEDED",
    )
    mock_client.start_run.return_value = handle
    mock_client.wait_for_run.return_value = handle
    mock_client.fetch_run_result.return_value = ActorRunResult(
        run_id="apify-obs-1",
        dataset_id="dataset-obs",
        key_value_store_id="kv-obs",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
        actor_output={"runStatus": "ok", "count": 3},
    )

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    claimed = service.runs.claim_next(lock_owner="obs", max_attempts=3)
    assert claimed is not None

    with caplog.at_level(logging.INFO, logger="app.services.collection"):
        service.execute_claimed_run(claimed.id)

    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded

    success_records = [
        r
        for r in caplog.records
        if getattr(r, "event", None) == "collection.succeeded"
    ]
    assert success_records
    record = success_records[-1]
    assert record.run_id == str(created.id)
    assert record.apify_run_id == "apify-obs-1"
    assert record.items_fetched == 3
    assert record.items_inserted == 3
    assert record.items_duplicated == 0
    assert record.items_invalid == 0
    assert isinstance(record.duration_ms, int)


def test_collection_failure_emits_structured_error_event(
    db_session: Session,
    caplog,
) -> None:
    from app.integrations.apify import ApifyIntegrationError

    mock_client = MagicMock()
    mock_client.start_run.side_effect = ApifyIntegrationError("boom-obs")

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 1})
    claimed = service.runs.claim_next(lock_owner="obs-fail", max_attempts=3)
    assert claimed is not None

    with caplog.at_level(logging.ERROR, logger="app.services.collection"):
        service.execute_claimed_run(claimed.id)

    fail_records = [
        r for r in caplog.records if getattr(r, "event", None) == "collection.failed"
    ]
    assert fail_records
    assert fail_records[-1].run_id == str(created.id)
    assert "boom-obs" in fail_records[-1].getMessage()
