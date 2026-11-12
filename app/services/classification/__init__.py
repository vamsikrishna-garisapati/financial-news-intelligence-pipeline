"""News classification services."""

from app.services.classification.service import ClassificationService, classify_article

__all__ = ["ClassificationService", "classify_article"]
