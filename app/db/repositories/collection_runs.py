"""Collection run persistence helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CollectionRun, CollectionRunStatus


class CollectionRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, input_payload: dict[str, Any]) -> CollectionRun:
        run = CollectionRun(
            status=CollectionRunStatus.pending,
            input_payload=input_payload,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get(self, run_id: uuid.UUID) -> CollectionRun | None:
        return self.db.get(CollectionRun, run_id)

    def mark_running(self, run_id: uuid.UUID) -> CollectionRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.status = CollectionRunStatus.running
        run.started_at = datetime.now(UTC)
        run.error_message = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_succeeded(
        self,
        run_id: uuid.UUID,
        *,
        apify_run_id: str | None,
        apify_dataset_id: str | None,
        actor_run_status: str | None,
        items_fetched: int,
        items_inserted: int,
        items_duplicated: int,
        items_invalid: int,
    ) -> CollectionRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.status = CollectionRunStatus.succeeded
        run.apify_run_id = apify_run_id
        run.apify_dataset_id = apify_dataset_id
        run.actor_run_status = actor_run_status
        run.items_fetched = items_fetched
        run.items_inserted = items_inserted
        run.items_duplicated = items_duplicated
        run.items_invalid = items_invalid
        run.finished_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_failed(self, run_id: uuid.UUID, error_message: str) -> CollectionRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.status = CollectionRunStatus.failed
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_recent(self, limit: int = 20) -> list[CollectionRun]:
        stmt = select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
