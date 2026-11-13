"""Collection run endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas.collection import CollectionRunCreate, CollectionRunResponse
from app.services.collection import CollectionService

router = APIRouter()

NotifyCollection = Callable[[uuid.UUID], None]


def notify_collection_run(_run_id: uuid.UUID) -> None:
    """Default: no-op. The in-process Postgres job worker claims pending runs."""


def get_collection_notifier() -> NotifyCollection:
    return notify_collection_run


# Backward-compatible alias used by older tests/docs.
def get_collection_scheduler() -> NotifyCollection:
    return notify_collection_run


@router.post(
    "/collection-runs",
    response_model=CollectionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_collection_run(
    payload: CollectionRunCreate,
    db: Session = Depends(get_session),
    notify: NotifyCollection = Depends(get_collection_notifier),
) -> CollectionRunResponse:
    service = CollectionService(db)
    run = service.create_run(payload.to_actor_input())
    notify(run.id)
    # Re-load in case an inline/test notifier already finished the run.
    refreshed = service.get_run(run.id) or run
    return CollectionRunResponse.model_validate(refreshed)


@router.get("/collection-runs/{run_id}", response_model=CollectionRunResponse)
def get_collection_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_session),
) -> CollectionRunResponse:
    service = CollectionService(db)
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection run not found",
        )
    return CollectionRunResponse.model_validate(run)
