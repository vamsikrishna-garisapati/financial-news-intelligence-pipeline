"""Deduplication unit tests."""

from datetime import UTC, datetime

import pytest
from app.services.deduplication import (
    canonicalize_url,
    content_fingerprint,
    resolve_dedupe_keys,
)


def test_canonicalize_url_strips_tracking_and_normalizes() -> None:
    url = "https://WWW.Example.com/news/story/?utm_source=rss&id=1#section"
    assert canonicalize_url(url) == "https://www.example.com/news/story?id=1"


def test_canonicalize_url_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        canonicalize_url("not-a-url")


def test_content_fingerprint_stable() -> None:
    published = datetime(2026, 10, 10, 20, 6, 24, tzinfo=UTC)
    first = content_fingerprint("Hello World", "CNBC", published)
    second = content_fingerprint("  hello   world ", "cnbc", published)
    assert first == second
    assert len(first) == 64


def test_resolve_dedupe_keys_prefers_dedupe_key() -> None:
    canonical, fingerprint = resolve_dedupe_keys(
        article_link="https://example.com/a?utm_source=x",
        dedupe_key="https://example.com/a",
        headline="Hello",
        source="CNBC",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert canonical == "https://example.com/a"
    assert fingerprint
