"""Shared pytest fixtures."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.api.deps import get_session
from app.api.routes.collection_runs import get_collection_scheduler
from app.db.base import Base
from app.integrations.apify import ActorRunResult
from app.main import create_app
from app.services.collection import CollectionService
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

FIXTURES = Path(__file__).parent / "fixtures"

TABLES = (
    "collection_run_articles",
    "article_companies",
    "articles",
    "companies",
    "collection_runs",
)


@pytest.fixture(scope="session")
def sample_articles() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "sample_articles.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def database_url() -> str:
    # Prefer a dedicated test DB so pytest never drops the app schema.
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://fnip:fnip@localhost:5433/fnip_test",
    )


@pytest.fixture(scope="session")
def engine(database_url: str):
    eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable for tests: {exc}")
    Base.metadata.drop_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TYPE IF EXISTS collection_run_status CASCADE"))
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TYPE IF EXISTS collection_run_status CASCADE"))
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    for table in TABLES:
        session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_apify_result(sample_articles: list[dict[str, Any]]) -> ActorRunResult:
    return ActorRunResult(
        run_id="apify-run-1",
        dataset_id="dataset-1",
        key_value_store_id="kv-1",
        status="SUCCEEDED",
        items=sample_articles,
        actor_run_status="ok",
    )


@pytest.fixture
def mock_apify_client(mock_apify_result: ActorRunResult) -> MagicMock:
    mock_client = MagicMock()
    mock_client.run_actor.return_value = mock_apify_result
    return mock_client


@pytest.fixture
def client(
    db_session: Session,
    mock_apify_client: MagicMock,
) -> Generator[TestClient, None, None]:
    app = create_app()

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    def _inline_scheduler(run_id: uuid.UUID, _background_tasks: BackgroundTasks) -> None:
        CollectionService(db_session, apify_client=mock_apify_client).execute_run(run_id)

    app.dependency_overrides[get_session] = _override_db
    app.dependency_overrides[get_collection_scheduler] = lambda: _inline_scheduler

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
