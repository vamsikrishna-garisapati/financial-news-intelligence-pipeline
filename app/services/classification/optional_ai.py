"""Optional AI classification stub — not used by default.

This module is intentionally separate from the rule-based classifier so AI
providers can be plugged in later without changing the collection pipeline.
"""

from __future__ import annotations

from typing import Any

from app.services.classification.base import Classifier, NewsCategory


class AIClassifier(Classifier):
    """Placeholder AI classifier.

    Enable only after configuring an external model provider. The default
    pipeline uses RuleBasedClassifier instead.
    """

    method = "ai_stub"

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def classify(
        self,
        *,
        headline: str,
        summary: str | None,
        actor_event_types: list[str],
        extra: dict[str, Any] | None = None,
    ) -> list[NewsCategory]:
        del headline, summary, actor_event_types, extra
        if not self.enabled:
            raise RuntimeError(
                "AIClassifier is disabled. Use RuleBasedClassifier or enable AI explicitly."
            )
        raise NotImplementedError("AI classification is not implemented in this MVP.")
