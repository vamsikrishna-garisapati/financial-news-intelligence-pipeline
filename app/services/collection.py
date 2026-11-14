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
from app.observability.logging import log_event
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
            log_event(
                logger,
                logging.ERROR,
                event="collection.not_found",
                message="Collection run not found",
                run_id=str(run_id),
            )
            return
        if run.status != CollectionRunStatus.running:
            claimed = self.runs.claim_run(
                run_id,
                lock_owner=lock_owner,
                max_attempts=self.settings.job_max_attempts,
            )
            if claimed is None:
                log_event(
                    logger,
                    logging.WARNING,
                    event="collection.claim_skipped",
                    message="Collection run could not be claimed",
                    run_id=str(run_id),
                    status=run.status.value,
                )
                return
            log_event(
                logger,
                logging.INFO,
                event="job.claimed",
                message="Claimed collection run",
                run_id=str(claimed.id),
                attempt_count=claimed.attempt_count,
                lock_owner=lock_owner,
            )
        self.execute_claimed_run(run_id)

    def execute_run(self, run_id: uuid.UUID) -> None:
        """Backward-compatible entry: claim then execute."""
        self.process_run(run_id, lock_owner="legacy")

    def execute_claimed_run(self, run_id: uuid.UUID) -> None:
        """Execute a run that is already claimed (`running`)."""
        run = self.runs.get(run_id)
        if run is None:
            log_event(
                logger,
                logging.ERROR,
                event="collection.not_found",
                message="Collection run not found",
                run_id=str(run_id),
            )
            return
        if run.status != CollectionRunStatus.running:
            log_event(
                logger,
                logging.ERROR,
                event="collection.not_running",
                message="Collection run is not in running state",
                run_id=str(run_id),
                status=run.status.value,
            )
            return

        try:
            self.runs.heartbeat(run_id)
            log_event(
                logger,
                logging.INFO,
                event="collection.heartbeat",
                message="Heartbeat before Apify work",
                run_id=str(run_id),
                apify_run_id=run.apify_run_id,
                attempt_count=run.attempt_count,
            )
            if run.apify_run_id:
                log_event(
                    logger,
                    logging.INFO,
                    event="collection.resume",
                    message="Resuming existing Apify run (no new Actor start)",
                    run_id=str(run_id),
                    apify_run_id=run.apify_run_id,
                )
                finished = self.apify_client.wait_for_run(run.apify_run_id)
            else:
                started = self.apify_client.start_run(run.input_payload)
                self.runs.set_apify_run(
                    run_id,
                    apify_run_id=started.run_id,
                    apify_dataset_id=started.dataset_id,
                )
                log_event(
                    logger,
                    logging.INFO,
                    event="collection.apify_started",
                    message="Started Apify Actor run and persisted run id",
                    run_id=str(run_id),
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
            succeeded = self.runs.mark_succeeded(
                run_id,
                apify_run_id=result.run_id,
                apify_dataset_id=result.dataset_id,
                actor_run_status=result.actor_run_status or result.status,
                items_fetched=len(result.items),
                items_inserted=inserted,
                items_duplicated=duplicated,
                items_invalid=len(errors),
                actor_output=result.actor_output,
                processing_errors=errors,
            )
            log_event(
                logger,
                logging.INFO,
                event="collection.succeeded",
                message="Collection run succeeded",
                run_id=str(run_id),
                apify_run_id=result.run_id,
                items_fetched=len(result.items),
                items_inserted=inserted,
                items_duplicated=duplicated,
                items_invalid=len(errors),
                duration_ms=succeeded.duration_ms if succeeded else None,
                actor_run_status=result.actor_run_status or result.status,
            )
            if errors:
                log_event(
                    logger,
                    logging.WARNING,
                    event="collection.processing_errors",
                    message="Collection run had invalid items",
                    run_id=str(run_id),
                    items_invalid=len(errors),
                    processing_errors=errors[:5],
                )
        except ApifyIntegrationError as exc:
            log_event(
                logger,
                logging.ERROR,
                event="collection.failed",
                message=f"Apify integration failed: {exc}",
                run_id=str(run_id),
                apify_run_id=run.apify_run_id,
                error_type="apify",
                exc_info=True,
            )
            self.db.rollback()
            self.runs.mark_failed(
                run_id,
                str(exc),
                retry_delay_secs=self.settings.job_retry_delay_secs,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger,
                logging.ERROR,
                event="collection.failed",
                message=f"Unexpected error: {exc}",
                run_id=str(run_id),
                apify_run_id=run.apify_run_id,
                error_type="unexpected",
                exc_info=True,
            )
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
