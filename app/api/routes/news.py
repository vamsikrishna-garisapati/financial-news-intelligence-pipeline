"""News search endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas.common import PaginatedResponse, PaginationMeta
from app.api.schemas.news import ArticleDetail, ArticleSummary
from app.db.repositories.articles import ArticleRepository

router = APIRouter()


@router.get("/news", response_model=PaginatedResponse[ArticleSummary])
def list_news(
    ticker: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    published_after: datetime | None = Query(default=None),
    published_before: datetime | None = Query(default=None),
    q: str | None = Query(default=None, description="Search headline and summary"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> PaginatedResponse[ArticleSummary]:
    repo = ArticleRepository(db)
    articles, total = repo.list_news(
        ticker=ticker,
        category=category,
        source=source,
        published_after=published_after,
        published_before=published_before,
        q=q,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[ArticleSummary.model_validate(article) for article in articles],
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/news/{article_id}", response_model=ArticleDetail)
def get_news_article(
    article_id: uuid.UUID,
    db: Session = Depends(get_session),
) -> ArticleDetail:
    repo = ArticleRepository(db)
    article = repo.get_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return ArticleDetail.model_validate(article)
