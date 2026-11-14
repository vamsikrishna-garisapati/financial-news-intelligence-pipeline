"""In-process job worker tests (mocked Apify only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.config import Settings
from app.db.models import CollectionRunStatus
from app.integrations.apify import ActorRunHandle, ActorRunResult
from app.services.collection import CollectionService
from app.services.job_worker import process_one_job
from sqlalchemy.orm import Session, sessionmaker


def _patch_session_local(monkeypatch, engine) -> None:
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.services.job_worker.SessionLocal", TestingSession)


def _mock_apify(sample_articles: list, *, run_id: str = "apify-worker-1") -> MagicMock:
    mock_client = MagicMock()
    handle = ActorRunHandle(
        run_id=run_id,
        dataset_id="dataset-worker-1",
        key_value_store_id="kv-worker-1",
        status="SUCCEEDED",
    )
    mock_client.start_run.return_value = handle
    mock_client.wait_for_run.return_value = handle
    mock_client.fetch_run_result.return_value = ActorRunResult(
        run_id=run_id,
        dataset_id="dataset-worker-1",
        key_value_store_id="kv-worker-1",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
        actor_output={"runStatus": "ok", "count": len(sample_articles)},
    )
    return mock_client


def test_process_one_job_returns_false_when_queue_empty(
    db_session: Session,
    engine,
    monkeypatch,
) -> None:
    _patch_session_local(monkeypatch, engine)
    assert process_one_job(lock_owner="empty-worker") is False


def test_process_one_job_claims_and_executes_with_mocked_apify(
    db_session: Session,
    engine,
    monkeypatch,
    sample_articles: list,
) -> None:
    _patch_session_local(monkeypatch, engine)
    mock_client = _mock_apify(sample_articles)

    service = CollectionService(db_session)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    db_session.commit()

    did_work = process_one_job(
        lock_owner="worker-exec",
        apify_client_factory=lambda: mock_client,
    )
    assert did_work is True
    mock_client.start_run.assert_called_once()
    mock_client.wait_for_run.assert_called_once_with("apify-worker-1")

    db_session.expire_all()
    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded
    assert finished.items_fetched == 3
    assert finished.apify_run_id == "apify-worker-1"


def test_process_one_job_recovers_stale_lease_and_resumes_without_start(
    db_session: Session,
    engine,
    monkeypatch,
    sample_articles: list,
) -> None:
    _patch_session_local(monkeypatch, engine)
    mock_client = _mock_apify(sample_articles, run_id="apify-resume-1")

    service = CollectionService(db_session)
    created = service.create_run({"feedPreset": "us_markets", "maxItems": 5})
    claimed = service.runs.claim_next(lock_owner="dead-worker", max_attempts=3)
    assert claimed is not None
    created.apify_run_id = "apify-resume-1"
    created.apify_dataset_id = "dataset-worker-1"
    stale = datetime.now(UTC) - timedelta(hours=1)
    created.heartbeat_at = stale
    created.locked_at = stale
    db_session.commit()

    settings = Settings(
        job_lease_seconds=60,
        job_max_attempts=3,
        job_worker_enabled=False,
        apify_token="test-token",
    )
    did_work = process_one_job(
        settings=settings,
        lock_owner="recovery-worker",
        apify_client_factory=lambda: mock_client,
    )
    assert did_work is True
    mock_client.start_run.assert_not_called()
    mock_client.wait_for_run.assert_called_once_with("apify-resume-1")

    db_session.expire_all()
    finished = service.get_run(created.id)
    assert finished is not None
    assert finished.status == CollectionRunStatus.succeeded
    assert finished.apify_run_id == "apify-resume-1"
