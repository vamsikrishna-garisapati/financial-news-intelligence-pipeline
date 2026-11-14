"""In-process Postgres-backed collection job poller."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from collections.abc import Callable

from app.config import Settings, get_settings
from app.db.session import SessionLocal
from app.observability.logging import log_event
from app.services.collection import CollectionService

logger = logging.getLogger(__name__)


def default_lock_owner() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def process_one_job(
    *,
    settings: Settings | None = None,
    lock_owner: str | None = None,
    apify_client_factory: Callable[[], object] | None = None,
) -> bool:
    """Recover stale leases and claim/execute at most one job. Returns True if work ran."""
    settings = settings or get_settings()
    owner = lock_owner or default_lock_owner()
    db = SessionLocal()
    try:
        service = CollectionService(db)
        if apify_client_factory is not None:
            service._apify_client = apify_client_factory()  # noqa: SLF001

        recovered = service.runs.recover_stale_leases(lease_seconds=settings.job_lease_seconds)
        if recovered:
            log_event(
                logger,
                logging.WARNING,
                event="job.recovered",
                message="Recovered abandoned collection job lease(s)",
                recovered_count=recovered,
                lock_owner=owner,
            )

        claimed = service.runs.claim_next(
            lock_owner=owner,
            max_attempts=settings.job_max_attempts,
        )
        if claimed is None:
            return False

        log_event(
            logger,
            logging.INFO,
            event="job.claimed",
            message="Claimed collection run",
            run_id=str(claimed.id),
            attempt_count=claimed.attempt_count,
            lock_owner=owner,
            apify_run_id=claimed.apify_run_id,
        )
        service.execute_claimed_run(claimed.id)
        return True
    finally:
        db.close()


async def job_worker_loop(
    stop_event: asyncio.Event,
    *,
    settings: Settings | None = None,
) -> None:
    """Poll Postgres for collection jobs until stop_event is set."""
    settings = settings or get_settings()
    owner = default_lock_owner()
    log_event(
        logger,
        logging.INFO,
        event="job.worker_started",
        message="Collection job worker started",
        lock_owner=owner,
        poll_interval_secs=settings.job_poll_interval_secs,
        lease_seconds=settings.job_lease_seconds,
    )
    try:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(
                    process_one_job,
                    settings=settings,
                    lock_owner=owner,
                )
            except Exception:  # noqa: BLE001
                log_event(
                    logger,
                    logging.ERROR,
                    event="job.worker_tick_failed",
                    message="Collection job worker tick failed",
                    lock_owner=owner,
                    exc_info=True,
                )
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.job_poll_interval_secs,
                )
            except TimeoutError:
                continue
    finally:
        log_event(
            logger,
            logging.INFO,
            event="job.worker_stopped",
            message="Collection job worker stopped",
            lock_owner=owner,
        )
