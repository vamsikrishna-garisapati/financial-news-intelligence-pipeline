"""Article processing and classification tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.services.classification.rules import RuleBasedClassifier
from app.services.processing import ArticleProcessor, ArticleValidationError


def test_normalize_valid_article(sample_articles: list[dict[str, Any]]) -> None:
    processor = ArticleProcessor()
    article = processor.normalize(sample_articles[1])
    assert article.headline.startswith("Apple reports")
    assert article.canonical_url == "https://cnbc.com/2026/10/09/apple-earnings.html"
    assert article.classification_method == "rules"
    assert "earnings" in article.categories
    assert article.companies[0].ticker == "AAPL"
    assert article.sentiment_label == "positive"


def test_normalize_rejects_missing_required_fields() -> None:
    processor = ArticleProcessor()
    with pytest.raises(ArticleValidationError):
        processor.normalize({"headline": "Only headline"})


def test_normalize_many_collects_errors(sample_articles: list[dict[str, Any]]) -> None:
    processor = ArticleProcessor()
    items = [*sample_articles, {"headline": "bad"}]
    normalized, errors = processor.normalize_many(items)
    assert len(normalized) == 3
    assert len(errors) == 1


def test_rule_classifier_maps_events_and_keywords() -> None:
    classifier = RuleBasedClassifier()
    categories = classifier.classify(
        headline="Company unveils new product launch",
        summary="The firm also faces an SEC investigation",
        actor_event_types=["mergers_acquisitions"],
    )
    values = {c.value for c in categories}
    assert "mergers_and_acquisitions" in values
    assert "product_launches" in values
    assert "regulatory_updates" in values


def test_rule_classifier_defaults_to_market_updates() -> None:
    classifier = RuleBasedClassifier()
    categories = classifier.classify(
        headline="Something unrelated",
        summary="",
        actor_event_types=[],
    )
    assert [c.value for c in categories] == ["market_updates"]
