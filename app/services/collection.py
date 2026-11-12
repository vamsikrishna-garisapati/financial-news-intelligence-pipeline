"""Orchestrate Apify collection runs and persistence."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories.articles import ArticleRepository
from app.db.repositories.collection_runs import CollectionRunRepository
from app.db.session import SessionLocal
from app.integrations.apify import ApifyIntegrationError, ApifyNewsClient
from app.services.processing import ArticleProcessor

logger = logging.getLogger(__name__)


class CollectionService:
    def __init__(
        self,
        db: Session,
        *,
        apify_client: ApifyNewsClient | None = None,
        processor: ArticleProcessor | None = None,
    ) -> None:
        self.db = db
        self.runs = CollectionRunRepository(db)
        self.articles = ArticleRepository(db)
        self._apify_client = apify_client
        self.processor = processor or ArticleProcessor()

    @property
    def apify_client(self) -> ApifyNewsClient:
        if self._apify_client is None:
            self._apify_client = ApifyNewsClient()
        return self._apify_client

    def create_run(self, input_payload: dict[str, Any]):
        return self.runs.create(input_payload)

    def get_run(self, run_id: uuid.UUID):
        return self.runs.get(run_id)

    def execute_run(self, run_id: uuid.UUID) -> None:
        run = self.runs.mark_running(run_id)
        if run is None:
            logger.error("Collection run %s not found", run_id)
            return

        try:
            result = self.apify_client.run_actor(run.input_payload)
            normalized, errors = self.processor.normalize_many(result.items)

            inserted = 0
            duplicated = 0
            for item in normalized:
                _article, was_inserted = self.articles.upsert_normalized(
                    item,
                    collection_run_id=run_id,
                )
                if was_inserted:
                    inserted += 1
                else:
                    duplicated += 1

            self.db.commit()
            self.runs.mark_succeeded(
                run_id,
                apify_run_id=result.run_id,
                apify_dataset_id=result.dataset_id,
                actor_run_status=result.actor_run_status or result.status,
                items_fetched=len(result.items),
                items_inserted=inserted,
                items_duplicated=duplicated,
                items_invalid=len(errors),
            )
            if errors:
                logger.warning(
                    "Collection run %s had %s invalid items: %s",
                    run_id,
                    len(errors),
                    errors[:5],
                )
        except ApifyIntegrationError as exc:
            logger.exception("Apify integration failed for run %s", run_id)
            self.db.rollback()
            self.runs.mark_failed(run_id, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected failure for collection run %s", run_id)
            self.db.rollback()
            self.runs.mark_failed(run_id, f"Unexpected error: {exc}")


def run_collection_in_background(run_id: uuid.UUID) -> None:
    """Entry point for FastAPI BackgroundTasks with its own DB session."""
    db = SessionLocal()
    try:
        CollectionService(db).execute_run(run_id)
    finally:
        db.close()
