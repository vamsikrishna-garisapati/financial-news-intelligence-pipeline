"""Company-scoped news endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas.common import PaginatedResponse, PaginationMeta
from app.api.schemas.news import ArticleSummary
from app.db.repositories.articles import ArticleRepository
from app.db.repositories.companies import CompanyRepository

router = APIRouter()


@router.get("/companies/{ticker}/news", response_model=PaginatedResponse[ArticleSummary])
def company_news(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> PaginatedResponse[ArticleSummary]:
    company = CompanyRepository(db).get_by_ticker(ticker)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    articles, total = ArticleRepository(db).list_for_ticker(
        ticker,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[ArticleSummary.model_validate(article) for article in articles],
        pagination=PaginationMeta(total=total, limit=limit, offset=offset),
    )
