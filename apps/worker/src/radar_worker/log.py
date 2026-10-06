"""Structured logging for the worker.

Key=value lines by default, JSON when RADAR_LOG_JSON=true.
Tokens and secrets must never be logged — callers are responsible for
redacting; this module just provides the format.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        parts = [f"ts={ts}", f"level={record.levelname}", f"logger={record.name}"]
        msg = record.getMessage().replace("\n", " ")
        parts.append(f"msg={msg!r}")
        for key in ("job", "repo", "extra"):
            if hasattr(record, key):
                parts.append(f"{key}={getattr(record, key)!r}")
        if record.exc_info and record.exc_info[0] is not None:
            parts.append(f"exc={self.formatException(record.exc_info)!r}")
        return " ".join(parts)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("job", "repo", "extra"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_format else KeyValueFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Quiet noisy libs; keep our own loggers at the configured level.
    for noisy in ("httpx", "httpcore", "apscheduler", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
