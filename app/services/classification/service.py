"""Classification service facade."""

from __future__ import annotations

from typing import Any

from app.services.classification.base import Classifier, NewsCategory
from app.services.classification.rules import RuleBasedClassifier


class ClassificationService:
    def __init__(self, classifier: Classifier | None = None) -> None:
        self.classifier = classifier or RuleBasedClassifier()

    @property
    def method(self) -> str:
        return getattr(self.classifier, "method", "unknown")

    def classify_article(
        self,
        *,
        headline: str,
        summary: str | None = None,
        actor_event_types: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> list[str]:
        categories = self.classifier.classify(
            headline=headline,
            summary=summary,
            actor_event_types=actor_event_types or [],
            extra=extra,
        )
        return [c.value if isinstance(c, NewsCategory) else str(c) for c in categories]


def classify_article(
    *,
    headline: str,
    summary: str | None = None,
    actor_event_types: list[str] | None = None,
) -> list[str]:
    return ClassificationService().classify_article(
        headline=headline,
        summary=summary,
        actor_event_types=actor_event_types,
    )
