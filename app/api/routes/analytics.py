"""Analytics endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas.analytics import CategoryVolumeItem, CategoryVolumeResponse, NewsVolumeResponse
from app.db.repositories.analytics import AnalyticsRepository

router = APIRouter()


@router.get("/analytics/news-volume", response_model=NewsVolumeResponse)
def news_volume(
    group_by: Literal["company", "date", "source"] = Query(...),
    published_after: datetime | None = Query(default=None),
    published_before: datetime | None = Query(default=None),
    ticker: str | None = Query(default=None),
    db: Session = Depends(get_session),
) -> NewsVolumeResponse:
    repo = AnalyticsRepository(db)
    try:
        items = repo.news_volume(
            group_by=group_by,
            published_after=published_after,
            published_before=published_before,
            ticker=ticker,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return NewsVolumeResponse(group_by=group_by, items=items)


@router.get("/analytics/categories", response_model=CategoryVolumeResponse)
def category_volume(
    published_after: datetime | None = Query(default=None),
    published_before: datetime | None = Query(default=None),
    db: Session = Depends(get_session),
) -> CategoryVolumeResponse:
    items = AnalyticsRepository(db).categories(
        published_after=published_after,
        published_before=published_before,
    )
    return CategoryVolumeResponse(items=[CategoryVolumeItem.model_validate(item) for item in items])
