"""Classification interfaces and category constants."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any


class NewsCategory(StrEnum):
    earnings = "earnings"
    mergers_and_acquisitions = "mergers_and_acquisitions"
    leadership_changes = "leadership_changes"
    regulatory_updates = "regulatory_updates"
    product_launches = "product_launches"
    market_updates = "market_updates"


class Classifier(ABC):
    method: str = "unknown"

    @abstractmethod
    def classify(
        self,
        *,
        headline: str,
        summary: str | None,
        actor_event_types: list[str],
        extra: dict[str, Any] | None = None,
    ) -> list[NewsCategory]:
        raise NotImplementedError
