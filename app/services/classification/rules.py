"""Rule-based financial news classifier."""

from __future__ import annotations

import re
from typing import Any

from app.services.classification.base import Classifier, NewsCategory

ACTOR_EVENT_TO_CATEGORY: dict[str, NewsCategory] = {
    "earnings": NewsCategory.earnings,
    "guidance": NewsCategory.earnings,
    "mergers_acquisitions": NewsCategory.mergers_and_acquisitions,
    "executive_change": NewsCategory.leadership_changes,
    "legal_regulatory": NewsCategory.regulatory_updates,
    "macro": NewsCategory.market_updates,
    "analyst_rating": NewsCategory.market_updates,
    "ipo": NewsCategory.market_updates,
    "dividends_buybacks": NewsCategory.market_updates,
    "layoffs_restructuring": NewsCategory.market_updates,
}

KEYWORD_RULES: list[tuple[NewsCategory, tuple[str, ...]]] = [
    (
        NewsCategory.earnings,
        (
            r"\bearnings?\b",
            r"\beps\b",
            r"\bguidance\b",
            r"\bquarterly results?\b",
            r"\brevenue\b",
        ),
    ),
    (
        NewsCategory.mergers_and_acquisitions,
        (
            r"\bmerger\b",
            r"\bacquisition\b",
            r"\bacquire[sd]?\b",
            r"\btakeover\b",
            r"\bbuyout\b",
            r"\bM&A\b",
        ),
    ),
    (
        NewsCategory.leadership_changes,
        (
            r"\bCEO\b",
            r"\bCFO\b",
            r"\bCOO\b",
            r"\bappoint(ed|s)?\b",
            r"\bresign(s|ed|ation)?\b",
            r"\bsteps? down\b",
            r"\bexecutive change\b",
        ),
    ),
    (
        NewsCategory.regulatory_updates,
        (
            r"\bSEC\b",
            r"\bFDA\b",
            r"\blawsuit\b",
            r"\bregulator(?:y|s)?\b",
            r"\binvestigation\b",
            r"\bfine[sd]?\b",
            r"\bantitrust\b",
        ),
    ),
    (
        NewsCategory.product_launches,
        (
            r"\blaunch(es|ed|ing)?\b",
            r"\bunveil(s|ed|ing)?\b",
            r"\bintroduces?\b",
            r"\bnew product\b",
            r"\brelease[sd]?\b",
        ),
    ),
    (
        NewsCategory.market_updates,
        (
            r"\bstock(s)?\b",
            r"\bmarket(s)?\b",
            r"\bindex(?:es)?\b",
            r"\bS&P\b",
            r"\bNasdaq\b",
            r"\bDow\b",
            r"\brally\b",
            r"\bsell[- ]?off\b",
        ),
    ),
]


class RuleBasedClassifier(Classifier):
    def classify(
        self,
        *,
        headline: str,
        summary: str | None,
        actor_event_types: list[str],
        extra: dict[str, Any] | None = None,
    ) -> list[NewsCategory]:
        del extra
        categories: set[NewsCategory] = set()

        for event in actor_event_types:
            mapped = ACTOR_EVENT_TO_CATEGORY.get(event)
            if mapped:
                categories.add(mapped)

        text = f"{headline} {summary or ''}"
        for category, patterns in KEYWORD_RULES:
            for pattern in patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    categories.add(category)
                    break

        if not categories:
            categories.add(NewsCategory.market_updates)

        return sorted(categories, key=lambda c: c.value)
