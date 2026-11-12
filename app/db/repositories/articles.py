"""Article persistence helpers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.db.models import Article, CollectionRunArticle, Company
from app.db.repositories.companies import CompanyRepository
from app.services.processing import NormalizedArticle


class ArticleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.companies = CompanyRepository(db)

    def get_by_id(self, article_id: uuid.UUID) -> Article | None:
        stmt = (
            select(Article).where(Article.id == article_id).options(selectinload(Article.companies))
        )
        return self.db.scalar(stmt)

    def find_existing(self, canonical_url: str, fingerprint: str) -> Article | None:
        stmt = select(Article).where(
            or_(
                Article.canonical_url == canonical_url,
                Article.content_fingerprint == fingerprint,
            )
        )
        return self.db.scalar(stmt)

    def upsert_normalized(
        self,
        normalized: NormalizedArticle,
        *,
        collection_run_id: uuid.UUID | None = None,
    ) -> tuple[Article, bool]:
        """Insert or return existing article. Returns (article, inserted)."""
        existing = self.find_existing(normalized.canonical_url, normalized.content_fingerprint)
        if existing is not None:
            if collection_run_id is not None:
                self._link_collection_run(existing.id, collection_run_id)
            company_models = self.companies.upsert_many(normalized.companies)
            for company in company_models:
                if company not in existing.companies:
                    existing.companies.append(company)
            self.db.flush()
            return existing, False

        article = Article(
            canonical_url=normalized.canonical_url,
            content_fingerprint=normalized.content_fingerprint,
            headline=normalized.headline,
            source=normalized.source,
            author=normalized.author,
            published_at=normalized.published_at,
            summary=normalized.summary,
            image_url=normalized.image_url,
            original_url=normalized.original_url,
            source_feed=normalized.source_feed,
            search_query=normalized.search_query,
            fetched_at=normalized.fetched_at,
            full_text=normalized.full_text,
            actor_event_types=normalized.actor_event_types,
            categories=normalized.categories,
            sentiment_score=normalized.sentiment_score,
            sentiment_label=normalized.sentiment_label,
            raw_payload=normalized.raw_payload,
        )
        self.db.add(article)
        self.db.flush()

        company_models = self.companies.upsert_many(normalized.companies)
        article.companies.extend(company_models)

        if collection_run_id is not None:
            self._link_collection_run(article.id, collection_run_id)

        self.db.flush()
        return article, True

    def _link_collection_run(self, article_id: uuid.UUID, collection_run_id: uuid.UUID) -> None:
        stmt = (
            pg_insert(CollectionRunArticle)
            .values(collection_run_id=collection_run_id, article_id=article_id)
            .on_conflict_do_nothing(
                index_elements=["collection_run_id", "article_id"],
            )
        )
        self.db.execute(stmt)

    def list_news(
        self,
        *,
        ticker: str | None = None,
        category: str | None = None,
        source: str | None = None,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Article], int]:
        stmt = select(Article).options(selectinload(Article.companies))
        stmt = self._apply_filters(
            stmt,
            ticker=ticker,
            category=category,
            source=source,
            published_after=published_after,
            published_before=published_before,
            q=q,
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(self.db.scalar(count_stmt) or 0)
        rows = self.db.scalars(
            stmt.order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total

    def list_for_ticker(
        self,
        ticker: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Article], int]:
        return self.list_news(ticker=ticker, limit=limit, offset=offset)

    def _apply_filters(
        self,
        stmt: Select[tuple[Article]],
        *,
        ticker: str | None,
        category: str | None,
        source: str | None,
        published_after: datetime | None,
        published_before: datetime | None,
        q: str | None,
    ) -> Select[tuple[Article]]:
        if ticker:
            stmt = stmt.join(Article.companies).where(Company.ticker == ticker.upper()).distinct()
        if category:
            stmt = stmt.where(Article.categories.contains([category]))
        if source:
            stmt = stmt.where(Article.source.ilike(f"%{source}%"))
        if published_after:
            stmt = stmt.where(Article.published_at >= published_after)
        if published_before:
            stmt = stmt.where(Article.published_at <= published_before)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(Article.headline.ilike(pattern), Article.summary.ilike(pattern)))
        return stmt
