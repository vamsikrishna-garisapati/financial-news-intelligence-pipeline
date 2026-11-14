"""Optional AI classifier stub tests."""

from __future__ import annotations

import pytest
from app.services.classification.optional_ai import AIClassifier


def test_ai_classifier_disabled_raises() -> None:
    classifier = AIClassifier(enabled=False)
    with pytest.raises(RuntimeError, match="disabled"):
        classifier.classify(headline="x", summary=None, actor_event_types=[])


def test_ai_classifier_enabled_not_implemented() -> None:
    classifier = AIClassifier(enabled=True)
    assert classifier.method == "ai_stub"
    with pytest.raises(NotImplementedError, match="not implemented"):
        classifier.classify(headline="x", summary=None, actor_event_types=[])
