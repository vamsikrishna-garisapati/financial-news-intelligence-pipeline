"""Database repository tests."""

from __future__ import annotations

from typing import Any

from app.db.repositories.articles import ArticleRepository
from app.services.processing import ArticleProcessor
from sqlalchemy.orm import Session


def test_article_upsert_deduplicates(
    db_session: Session,
    sample_articles: list[dict[str, Any]],
) -> None:
    processor = ArticleProcessor()
    repo = ArticleRepository(db_session)
    normalized = processor.normalize(sample_articles[0])

    first, inserted_first = repo.upsert_normalized(normalized)
    db_session.commit()
    second, inserted_second = repo.upsert_normalized(normalized)
    db_session.commit()

    assert inserted_first is True
    assert inserted_second is False
    assert first.id == second.id
    assert first.companies[0].ticker == "NVDA"


def test_fingerprint_collision_treated_as_duplicate(
    db_session: Session, sample_articles: list[dict[str, Any]]
) -> None:
    processor = ArticleProcessor()
    repo = ArticleRepository(db_session)
    base = processor.normalize(sample_articles[1])
    repo.upsert_normalized(base)
    db_session.commit()

    # Same headline/source/date but different URL should still match fingerprint unique path
    # only if URL is new AND fingerprint matches — find_existing checks OR.
    clone_payload = dict(sample_articles[1])
    clone_payload["articleLink"] = "https://www.cnbc.com/2026/10/09/apple-earnings-mirror.html"
    clone_payload["dedupeKey"] = clone_payload["articleLink"]
    clone = processor.normalize(clone_payload)
    # Force identical fingerprint by reusing base fingerprint after normalize
    clone.content_fingerprint = base.content_fingerprint

    article, inserted = repo.upsert_normalized(clone)
    db_session.commit()
    assert inserted is False
    assert article.id is not None
