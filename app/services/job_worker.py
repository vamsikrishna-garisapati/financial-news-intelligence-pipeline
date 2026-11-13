"""In-process Postgres-backed collection job poller."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from collections.abc import Callable

from app.config import Settings, get_settings
from app.db.session import SessionLocal
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
            logger.warning("Recovered %s abandoned collection job(s)", recovered)

        claimed = service.runs.claim_next(
            lock_owner=owner,
            max_attempts=settings.job_max_attempts,
        )
        if claimed is None:
            return False

        logger.info("Claimed collection run %s attempt=%s", claimed.id, claimed.attempt_count)
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
    logger.info(
        "Collection job worker started owner=%s poll=%ss lease=%ss",
        owner,
        settings.job_poll_interval_secs,
        settings.job_lease_seconds,
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
                logger.exception("Collection job worker tick failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.job_poll_interval_secs,
                )
            except TimeoutError:
                continue
    finally:
        logger.info("Collection job worker stopped owner=%s", owner)
