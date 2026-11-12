"""Analytics queries for news volume and categories."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import Article, Company


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def news_volume(
        self,
        *,
        group_by: str,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        if group_by == "company":
            return self._volume_by_company(
                published_after=published_after,
                published_before=published_before,
                ticker=ticker,
            )
        if group_by == "date":
            return self._volume_by_date(
                published_after=published_after,
                published_before=published_before,
                ticker=ticker,
            )
        if group_by == "source":
            return self._volume_by_source(
                published_after=published_after,
                published_before=published_before,
                ticker=ticker,
            )
        raise ValueError(f"Unsupported group_by: {group_by}")

    def categories(
        self,
        *,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(Article.categories, Article.id)
        if published_after:
            stmt = stmt.where(Article.published_at >= published_after)
        if published_before:
            stmt = stmt.where(Article.published_at <= published_before)

        counts: dict[str, int] = {}
        for categories, _article_id in self.db.execute(stmt).all():
            for category in categories or []:
                key = str(category)
                counts[key] = counts.get(key, 0) + 1

        return [
            {"category": category, "count": count}
            for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _volume_by_company(
        self,
        *,
        published_after: datetime | None,
        published_before: datetime | None,
        ticker: str | None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Company.ticker, Company.name, func.count(Article.id).label("count"))
            .join(Article.companies)
            .group_by(Company.ticker, Company.name)
            .order_by(func.count(Article.id).desc(), Company.ticker.asc())
        )
        if published_after:
            stmt = stmt.where(Article.published_at >= published_after)
        if published_before:
            stmt = stmt.where(Article.published_at <= published_before)
        if ticker:
            stmt = stmt.where(Company.ticker == ticker.upper())

        return [
            {"ticker": row.ticker, "name": row.name, "count": int(row.count)}
            for row in self.db.execute(stmt).all()
        ]

    def _volume_by_date(
        self,
        *,
        published_after: datetime | None,
        published_before: datetime | None,
        ticker: str | None,
    ) -> list[dict[str, Any]]:
        day = cast(Article.published_at, Date).label("day")
        stmt = select(day, func.count(Article.id).label("count")).group_by(day).order_by(day.asc())
        if published_after:
            stmt = stmt.where(Article.published_at >= published_after)
        if published_before:
            stmt = stmt.where(Article.published_at <= published_before)
        if ticker:
            stmt = stmt.join(Article.companies).where(Company.ticker == ticker.upper())

        return [
            {"date": row.day.isoformat() if row.day else None, "count": int(row.count)}
            for row in self.db.execute(stmt).all()
            if row.day is not None
        ]

    def _volume_by_source(
        self,
        *,
        published_after: datetime | None,
        published_before: datetime | None,
        ticker: str | None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Article.source, func.count(Article.id).label("count"))
            .group_by(Article.source)
            .order_by(func.count(Article.id).desc(), Article.source.asc())
        )
        if published_after:
            stmt = stmt.where(Article.published_at >= published_after)
        if published_before:
            stmt = stmt.where(Article.published_at <= published_before)
        if ticker:
            stmt = stmt.join(Article.companies).where(Company.ticker == ticker.upper()).distinct()

        # Re-build without distinct for aggregate correctness when ticker filter is used.
        if ticker:
            stmt = (
                select(Article.source, func.count(func.distinct(Article.id)).label("count"))
                .join(Article.companies)
                .where(Company.ticker == ticker.upper())
                .group_by(Article.source)
                .order_by(func.count(func.distinct(Article.id)).desc(), Article.source.asc())
            )
            if published_after:
                stmt = stmt.where(Article.published_at >= published_after)
            if published_before:
                stmt = stmt.where(Article.published_at <= published_before)

        return [
            {"source": row.source, "count": int(row.count)} for row in self.db.execute(stmt).all()
        ]
