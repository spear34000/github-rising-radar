"""Process-local API usage counters.

These back the ``api_calls_24h`` field of ``GET /api/stats``. Counters are
in-memory and reset on restart; with multiple API replicas the value is a
lower bound. This is an MVP trade-off, documented in the API: for exact
numbers a persistent request-log table would be needed.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()
_calls: deque[datetime] = deque()
_WINDOW = timedelta(hours=24)


def record_call(now: datetime | None = None) -> None:
    ts = now or datetime.now(timezone.utc)
    with _lock:
        _calls.append(ts)
        _prune_locked(ts)


def calls_last_24h(now: datetime | None = None) -> int:
    ts = now or datetime.now(timezone.utc)
    with _lock:
        _prune_locked(ts)
        return len(_calls)


def _prune_locked(now: datetime) -> None:
    cutoff = now - _WINDOW
    while _calls and _calls[0] < cutoff:
        _calls.popleft()
