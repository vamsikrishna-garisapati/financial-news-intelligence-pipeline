"""Guardrail: automated tests must never construct a live Apify client unexpectedly."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.collection import CollectionService
from sqlalchemy.orm import Session


def test_collection_service_does_not_construct_apify_client_when_injected(
    db_session: Session,
    sample_articles: list,
) -> None:
    mock_client = MagicMock()
    handle = MagicMock()
    handle.run_id = "x"
    handle.dataset_id = "d"
    handle.key_value_store_id = "k"
    handle.status = "SUCCEEDED"
    mock_client.start_run.return_value = handle
    mock_client.wait_for_run.return_value = handle
    mock_client.fetch_run_result.return_value = MagicMock(
        run_id="x",
        dataset_id="d",
        key_value_store_id="k",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
        actor_output={"runStatus": "ok"},
    )

    with patch("app.integrations.apify.ApifyClient") as client_cls:
        service = CollectionService(db_session, apify_client=mock_client)
        created = service.create_run({"feedPreset": "us_markets", "maxItems": 1})
        claimed = service.runs.claim_next(lock_owner="guard", max_attempts=3)
        assert claimed is not None
        service.execute_claimed_run(created.id)
        client_cls.assert_not_called()
