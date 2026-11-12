"""Collection run endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas.collection import CollectionRunCreate, CollectionRunResponse
from app.services.collection import CollectionService, run_collection_in_background

router = APIRouter()

ScheduleCollection = Callable[[uuid.UUID, BackgroundTasks], None]


def schedule_collection_run(run_id: uuid.UUID, background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(run_collection_in_background, run_id)


def get_collection_scheduler() -> ScheduleCollection:
    return schedule_collection_run


@router.post(
    "/collection-runs",
    response_model=CollectionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_collection_run(
    payload: CollectionRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    schedule: ScheduleCollection = Depends(get_collection_scheduler),
) -> CollectionRunResponse:
    service = CollectionService(db)
    run = service.create_run(payload.to_actor_input())
    schedule(run.id, background_tasks)
    # Re-load in case an inline/test scheduler already finished the run.
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
