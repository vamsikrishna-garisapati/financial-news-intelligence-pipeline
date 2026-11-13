"""Collection run persistence helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import CollectionRun, CollectionRunStatus


class CollectionRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        input_payload: dict[str, Any],
        *,
        max_attempts: int = 3,
    ) -> CollectionRun:
        run = CollectionRun(
            status=CollectionRunStatus.pending,
            input_payload=input_payload,
            max_attempts=max_attempts,
            attempt_count=0,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get(self, run_id: uuid.UUID) -> CollectionRun | None:
        return self.db.get(CollectionRun, run_id)

    def _claimable_filter(self, *, now: datetime):
        return or_(
            CollectionRun.status == CollectionRunStatus.pending,
            and_(
                CollectionRun.status == CollectionRunStatus.failed,
                CollectionRun.attempt_count < CollectionRun.max_attempts,
                or_(
                    CollectionRun.next_attempt_at.is_(None),
                    CollectionRun.next_attempt_at <= now,
                ),
            ),
        )

    def _apply_claim(self, run: CollectionRun, *, lock_owner: str, now: datetime) -> CollectionRun:
        run.status = CollectionRunStatus.running
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.lock_owner = lock_owner
        run.locked_at = now
        run.heartbeat_at = now
        run.next_attempt_at = None
        run.error_message = None
        run.finished_at = None
        if run.started_at is None:
            run.started_at = now
        self.db.commit()
        self.db.refresh(run)
        return run

    def claim_next(self, *, lock_owner: str, max_attempts: int) -> CollectionRun | None:
        """Claim the oldest pending/retryable run using SKIP LOCKED."""
        del max_attempts  # per-row max_attempts is authoritative
        now = datetime.now(UTC)
        stmt = (
            select(CollectionRun)
            .where(self._claimable_filter(now=now))
            .order_by(CollectionRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = self.db.scalars(stmt).first()
        if run is None:
            return None
        return self._apply_claim(run, lock_owner=lock_owner, now=now)

    def claim_run(
        self,
        run_id: uuid.UUID,
        *,
        lock_owner: str,
        max_attempts: int,
    ) -> CollectionRun | None:
        """Claim a specific run if it is pending or retryable."""
        del max_attempts
        now = datetime.now(UTC)
        stmt = (
            select(CollectionRun)
            .where(
                CollectionRun.id == run_id,
                self._claimable_filter(now=now),
            )
            .with_for_update(skip_locked=True)
        )
        run = self.db.scalars(stmt).first()
        if run is None:
            return None
        return self._apply_claim(run, lock_owner=lock_owner, now=now)

    def heartbeat(self, run_id: uuid.UUID) -> None:
        run = self.get(run_id)
        if run is None or run.status != CollectionRunStatus.running:
            return
        run.heartbeat_at = datetime.now(UTC)
        self.db.commit()

    def set_apify_run(
        self,
        run_id: uuid.UUID,
        *,
        apify_run_id: str,
        apify_dataset_id: str | None,
    ) -> CollectionRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.apify_run_id = apify_run_id
        run.apify_dataset_id = apify_dataset_id
        run.heartbeat_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(run)
        return run

    def clear_lease(self, run: CollectionRun) -> None:
        run.lock_owner = None
        run.locked_at = None
        run.heartbeat_at = None

    def recover_stale_leases(self, *, lease_seconds: int) -> int:
        """Requeue or fail running jobs whose heartbeat is older than the lease."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=lease_seconds)
        stmt = (
            select(CollectionRun)
            .where(
                CollectionRun.status == CollectionRunStatus.running,
                or_(
                    and_(
                        CollectionRun.heartbeat_at.is_not(None),
                        CollectionRun.heartbeat_at < cutoff,
                    ),
                    and_(
                        CollectionRun.heartbeat_at.is_(None),
                        CollectionRun.locked_at.is_not(None),
                        CollectionRun.locked_at < cutoff,
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
        )
        stale_runs = list(self.db.scalars(stmt).all())
        for run in stale_runs:
            self.clear_lease(run)
            if run.attempt_count >= run.max_attempts:
                run.status = CollectionRunStatus.failed
                run.error_message = "Abandoned: job lease expired after max attempts"
                run.finished_at = now
                run.next_attempt_at = None
                run.duration_ms = self._duration_ms(run, now)
            else:
                run.status = CollectionRunStatus.pending
                run.error_message = "Lease expired; requeued for retry"
                run.next_attempt_at = now
                run.finished_at = None
        if stale_runs:
            self.db.commit()
        return len(stale_runs)

    def mark_running(self, run_id: uuid.UUID) -> CollectionRun | None:
        """Legacy helper — prefer claim_next/claim_run for new code paths."""
        return self.claim_run(run_id, lock_owner="legacy", max_attempts=3)

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
        now = datetime.now(UTC)
        run.status = CollectionRunStatus.succeeded
        run.apify_run_id = apify_run_id
        run.apify_dataset_id = apify_dataset_id
        run.actor_run_status = actor_run_status
        run.items_fetched = items_fetched
        run.items_inserted = items_inserted
        run.items_duplicated = items_duplicated
        run.items_invalid = items_invalid
        run.finished_at = now
        run.duration_ms = self._duration_ms(run, now)
        run.next_attempt_at = None
        run.error_message = None
        self.clear_lease(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_failed(
        self,
        run_id: uuid.UUID,
        error_message: str,
        *,
        retry_delay_secs: int | None = None,
    ) -> CollectionRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        now = datetime.now(UTC)
        run.status = CollectionRunStatus.failed
        run.error_message = error_message
        run.finished_at = now
        run.duration_ms = self._duration_ms(run, now)
        self.clear_lease(run)
        can_retry = run.attempt_count < run.max_attempts
        if can_retry and retry_delay_secs is not None:
            run.next_attempt_at = now + timedelta(seconds=retry_delay_secs)
        else:
            run.next_attempt_at = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_recent(self, limit: int = 20) -> list[CollectionRun]:
        stmt = select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    @staticmethod
    def _duration_ms(run: CollectionRun, finished_at: datetime) -> int | None:
        if run.started_at is None:
            return None
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return max(0, int((finished_at - started).total_seconds() * 1000))
