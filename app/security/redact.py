"""Redact secrets from log messages."""

from __future__ import annotations

import logging
import re

from app.config import get_settings

_REDACTED = "***"
_SKIP_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
}


def redact_secrets(text: str, secrets: list[str | None]) -> str:
    """Replace known secret values in text. Longer secrets first to avoid partial misses."""
    redacted = text
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, _REDACTED)
    # Common env-style assignments if value somehow differs
    redacted = re.sub(
        r"(?i)\b(apify_token|authorization|api[_-]?key)\s*[=:]\s*\S+",
        r"\1=***",
        redacted,
    )
    return redacted


class RedactingFilter(logging.Filter):
    """Logging filter that strips APIFY_TOKEN and similar secrets from records."""

    def filter(self, record: logging.LogRecord) -> bool:
        settings = get_settings()
        secrets = [settings.apify_token]
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg, secrets)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_secrets(value, secrets) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(arg, secrets) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        for key, value in list(record.__dict__.items()):
            if key in _SKIP_ATTRS or key.startswith("_"):
                continue
            if isinstance(value, str):
                setattr(record, key, redact_secrets(value, secrets))
        return True
