"""Orchestrate Apify collection runs and persistence."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CollectionRunStatus
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
        self.settings = get_settings()

    @property
    def apify_client(self) -> ApifyNewsClient:
        if self._apify_client is None:
            self._apify_client = ApifyNewsClient()
        return self._apify_client

    def create_run(self, input_payload: dict[str, Any], *, max_attempts: int | None = None):
        attempts = (
            max_attempts if max_attempts is not None else self.settings.job_max_attempts
        )
        return self.runs.create(input_payload, max_attempts=attempts)

    def get_run(self, run_id: uuid.UUID):
        return self.runs.get(run_id)

    def process_run(self, run_id: uuid.UUID, *, lock_owner: str = "inline") -> None:
        """Claim a specific pending/retryable run (if needed) and execute it."""
        run = self.runs.get(run_id)
        if run is None:
            logger.error("Collection run %s not found", run_id)
            return
        if run.status != CollectionRunStatus.running:
            claimed = self.runs.claim_run(
                run_id,
                lock_owner=lock_owner,
                max_attempts=self.settings.job_max_attempts,
            )
            if claimed is None:
                logger.warning(
                    "Collection run %s could not be claimed (status=%s)",
                    run_id,
                    run.status,
                )
                return
        self.execute_claimed_run(run_id)

    def execute_run(self, run_id: uuid.UUID) -> None:
        """Backward-compatible entry: claim then execute."""
        self.process_run(run_id, lock_owner="legacy")

    def execute_claimed_run(self, run_id: uuid.UUID) -> None:
        """Execute a run that is already claimed (`running`)."""
        run = self.runs.get(run_id)
        if run is None:
            logger.error("Collection run %s not found", run_id)
            return
        if run.status != CollectionRunStatus.running:
            logger.error("Collection run %s is not running (status=%s)", run_id, run.status)
            return

        try:
            self.runs.heartbeat(run_id)
            if run.apify_run_id:
                logger.info(
                    "Resuming Apify run %s for collection run %s (no new Actor start)",
                    run.apify_run_id,
                    run_id,
                )
                finished = self.apify_client.wait_for_run(run.apify_run_id)
            else:
                started = self.apify_client.start_run(run.input_payload)
                self.runs.set_apify_run(
                    run_id,
                    apify_run_id=started.run_id,
                    apify_dataset_id=started.dataset_id,
                )
                self.runs.heartbeat(run_id)
                finished = self.apify_client.wait_for_run(started.run_id)

            self.runs.heartbeat(run_id)
            result = self.apify_client.fetch_run_result(finished)
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
            logger.info(
                "Collection run %s succeeded fetched=%s inserted=%s duplicated=%s invalid=%s",
                run_id,
                len(result.items),
                inserted,
                duplicated,
                len(errors),
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
            self.runs.mark_failed(
                run_id,
                str(exc),
                retry_delay_secs=self.settings.job_retry_delay_secs,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected failure for collection run %s", run_id)
            self.db.rollback()
            self.runs.mark_failed(
                run_id,
                f"Unexpected error: {exc}",
                retry_delay_secs=self.settings.job_retry_delay_secs,
            )


def run_collection_in_background(run_id: uuid.UUID) -> None:
    """Process a single run with its own DB session (tests / manual enqueue)."""
    db = SessionLocal()
    try:
        CollectionService(db).process_run(run_id, lock_owner="background")
    finally:
        db.close()
