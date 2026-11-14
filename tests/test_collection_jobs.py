"""Persistent collection job claim, recovery, and Apify resume tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.db.models import CollectionRunStatus
from app.db.repositories.collection_runs import CollectionRunRepository
from app.integrations.apify import ActorRunHandle, ActorRunResult, ApifyIntegrationError
from app.services.collection import CollectionService
from sqlalchemy.orm import Session


def test_claim_next_marks_pending_run_running(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    created = repo.create({"feedPreset": "us_markets", "maxItems": 1})

    claimed = repo.claim_next(lock_owner="worker-1", max_attempts=3)

    assert claimed is not None
    assert claimed.id == created.id
    assert claimed.status == CollectionRunStatus.running
    assert claimed.attempt_count == 1
    assert claimed.lock_owner == "worker-1"
    assert claimed.locked_at is not None
    assert claimed.heartbeat_at is not None
    assert claimed.started_at is not None


def test_claim_next_skips_locked_row(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    first = repo.create({"feedPreset": "us_markets", "maxItems": 1})
    second = repo.create({"feedPreset": "us_markets", "maxItems": 2})

    claimed_a = repo.claim_next(lock_owner="worker-a", max_attempts=3)
    claimed_b = repo.claim_next(lock_owner="worker-b", max_attempts=3)

    assert claimed_a is not None and claimed_a.id == first.id
    assert claimed_b is not None and claimed_b.id == second.id


def test_recover_stale_leases_requeues_running_job(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    run = repo.create({"feedPreset": "us_markets", "maxItems": 1})
    claimed = repo.claim_next(lock_owner="dead-worker", max_attempts=3)
    assert claimed is not None

    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    claimed.locked_at = stale_time
    claimed.heartbeat_at = stale_time
    db_session.commit()

    recovered = repo.recover_stale_leases(lease_seconds=60)
    refreshed = repo.get(run.id)

    assert recovered == 1
    assert refreshed is not None
    assert refreshed.status == CollectionRunStatus.pending
    assert refreshed.lock_owner is None
    assert refreshed.locked_at is None
    assert refreshed.attempt_count == 1


def test_recover_stale_leases_fails_when_attempts_exhausted(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    run = repo.create({"feedPreset": "us_markets", "maxItems": 1}, max_attempts=1)
    claimed = repo.claim_next(lock_owner="dead-worker", max_attempts=1)
    assert claimed is not None
    assert claimed.attempt_count == 1

    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    claimed.heartbeat_at = stale_time
    claimed.locked_at = stale_time
    db_session.commit()

    recovered = repo.recover_stale_leases(lease_seconds=60)
    refreshed = repo.get(run.id)

    assert recovered == 1
    assert refreshed is not None
    assert refreshed.status == CollectionRunStatus.failed
    assert refreshed.error_message is not None
    message = refreshed.error_message.lower()
    assert "lease" in message or "abandoned" in message


def test_execute_starts_apify_and_persists_run_id_before_wait(
    db_session: Session,
    sample_articles: list,
) -> None:
    mock_client = MagicMock()
    mock_client.start_run.return_value = ActorRunHandle(
        run_id="apify-run-new",
        dataset_id="dataset-new",
        key_value_store_id="kv-new",
        status="RUNNING",
    )
    mock_client.wait_for_run.return_value = ActorRunHandle(
        run_id="apify-run-new",
        dataset_id="dataset-new",
        key_value_store_id="kv-new",
        status="SUCCEEDED",
    )
    mock_client.fetch_run_result.return_value = ActorRunResult(
        run_id="apify-run-new",
        dataset_id="dataset-new",
        key_value_store_id="kv-new",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
    )

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    claimed = service.runs.claim_next(lock_owner="test", max_attempts=3)
    assert claimed is not None

    service.execute_claimed_run(claimed.id)

    mock_client.start_run.assert_called_once()
    mock_client.wait_for_run.assert_called_once_with("apify-run-new")
    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded
    assert finished.apify_run_id == "apify-run-new"
    assert finished.duration_ms is not None
    assert finished.duration_ms >= 0


def test_execute_resumes_existing_apify_run_without_starting(
    db_session: Session,
    sample_articles: list,
) -> None:
    mock_client = MagicMock()
    mock_client.wait_for_run.return_value = ActorRunHandle(
        run_id="apify-run-existing",
        dataset_id="dataset-existing",
        key_value_store_id="kv-existing",
        status="SUCCEEDED",
    )
    mock_client.fetch_run_result.return_value = ActorRunResult(
        run_id="apify-run-existing",
        dataset_id="dataset-existing",
        key_value_store_id="kv-existing",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
    )

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    created.apify_run_id = "apify-run-existing"
    created.apify_dataset_id = "dataset-existing"
    db_session.commit()

    claimed = service.runs.claim_next(lock_owner="test", max_attempts=3)
    assert claimed is not None
    service.execute_claimed_run(claimed.id)

    mock_client.start_run.assert_not_called()
    mock_client.wait_for_run.assert_called_once_with("apify-run-existing")
    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded
    assert finished.items_fetched == 3


def test_execute_schedules_retry_on_failure(db_session: Session) -> None:
    mock_client = MagicMock()
    mock_client.start_run.side_effect = ApifyIntegrationError("temporary")

    service = CollectionService(db_session, apify_client=mock_client)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 1}, max_attempts=3)
    claimed = service.runs.claim_next(lock_owner="test", max_attempts=3)
    assert claimed is not None

    service.execute_claimed_run(claimed.id)

    failed = service.get_run(created.id)
    assert failed is not None
    assert failed.status == CollectionRunStatus.failed
    assert failed.next_attempt_at is not None
    assert failed.attempt_count == 1
    assert failed.lock_owner is None


def test_claim_next_picks_retryable_failed_run(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    run = repo.create({"feedPreset": "us_markets", "maxItems": 1}, max_attempts=3)
    run.status = CollectionRunStatus.failed
    run.attempt_count = 1
    run.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    claimed = repo.claim_next(lock_owner="worker-retry", max_attempts=3)

    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.status == CollectionRunStatus.running
    assert claimed.attempt_count == 2


def test_claim_specific_run_for_inline_tests(db_session: Session) -> None:
    repo = CollectionRunRepository(db_session)
    run = repo.create({"feedPreset": "us_markets", "maxItems": 1})

    claimed = repo.claim_run(run.id, lock_owner="inline", max_attempts=3)

    assert claimed is not None
    assert claimed.status == CollectionRunStatus.running
    assert repo.claim_next(lock_owner="other", max_attempts=3) is None
