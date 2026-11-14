"""URL canonicalization and content fingerprint helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "si",
}


def _strip_default_port(scheme: str, netloc: str) -> str:
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[: -len(":80")]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[: -len(":443")]
    return netloc


def _strip_www(netloc: str) -> str:
    """Strip a single leading www. host label. Other subdomains are preserved."""
    host, sep, port = netloc.partition(":")
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{sep}{port}" if sep else host


def canonicalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    - lowercases scheme/host
    - strips fragments
    - collapses repeated slashes and trailing slash (except root)
    - removes common tracking query params
    - sorts remaining query params
    - drops default ports (:80 / :443)
    - strips a single leading ``www.`` label
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url!r}")

    scheme = parsed.scheme.lower()
    netloc = _strip_www(_strip_default_port(scheme, parsed.netloc.lower()))
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_QUERY_KEYS or any(
            lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES
        ):
            continue
        query_pairs.append((key, value))
    query_pairs.sort(key=lambda pair: (pair[0].lower(), pair[1]))
    query = urlencode(query_pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def content_fingerprint(
    headline: str,
    source: str,
    published_at: datetime | date | None,
) -> str:
    """Fallback fingerprint when URL-based dedupe is insufficient.

    Missing ``published_at`` uses the literal day token ``unknown``.
    """
    if isinstance(published_at, datetime):
        day = published_at.date().isoformat()
    elif isinstance(published_at, date):
        day = published_at.isoformat()
    else:
        day = "unknown"
    payload = f"{normalize_text(headline)}|{normalize_text(source)}|{day}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_dedupe_keys(
    *,
    article_link: str,
    dedupe_key: str | None,
    headline: str,
    source: str,
    published_at: datetime | None,
) -> tuple[str, str]:
    """Return (canonical_url, content_fingerprint). Prefer Actor dedupeKey when present."""
    preferred = (dedupe_key or article_link).strip()
    try:
        canonical = canonicalize_url(preferred)
    except ValueError:
        canonical = canonicalize_url(article_link)
    fingerprint = content_fingerprint(headline, source, published_at)
    return canonical, fingerprint
