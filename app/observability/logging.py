"""Structured logging helpers using the stdlib logging module."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

from app.security.redact import RedactingFilter

_STANDARD_RECORD_ATTRS = {
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
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key.startswith("_"):
                continue
            if value is None:
                continue
            payload[key] = value

        return json.dumps(payload, default=str, ensure_ascii=False)


def log_event(
    logger: logging.Logger,
    level: int,
    *,
    event: str,
    message: str,
    exc_info: bool | None = None,
    **fields: Any,
) -> None:
    """Log a structured event with stable field names for collection observability."""
    extra = {"event": event, **fields}
    logger.log(level, message, exc_info=exc_info, extra=extra)


def configure_logging(
    level_name: str = "INFO",
    *,
    log_format: str = "json",
    stream: TextIO | None = None,
) -> None:
    """Configure root logging with JSON or plain text and secret redaction."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Replace existing handlers so reconfigure is deterministic (tests / reload).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(level)
    if log_format.lower() == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
