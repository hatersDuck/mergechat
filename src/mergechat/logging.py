"""JSON structured logging with basic secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s\-()]{7,}\d)(?!\w)")
_SECRET_RE = re.compile(
    r"(?i)\b(token|password|authorization|api[_-]?key|secret)\b\s*[=:]\s*\S+"
)


def redact(value: str) -> str:
    """Redact phone numbers and obvious key/value secrets from a string."""
    value = _SECRET_RE.sub(r"\1=[REDACTED]", value)
    return _PHONE_RE.sub("[REDACTED_PHONE]", value)


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
            }:
                continue
            if key.startswith("_"):
                continue
            payload[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once with a JSON formatter."""
    root = logging.getLogger()
    desired_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(desired_level)

    if any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        for handler in root.handlers:
            if isinstance(handler.formatter, JsonFormatter):
                handler.setLevel(desired_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(desired_level)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
