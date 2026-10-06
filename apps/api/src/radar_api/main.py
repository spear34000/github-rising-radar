"""FastAPI application factory."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import metrics as api_metrics
from .config import settings
from .logging import configure_logging
from .routers import admin, rankings, repos, stats

log = logging.getLogger("radar_api")

# --- simple per-IP sliding-window rate limiter -------------------------------
# In-memory and process-local (documented trade-off; good enough for the MVP
# behind a single replica; use a shared store when scaling out).
_rl_lock = threading.Lock()
_rl_hits: dict[str, deque[float]] = {}
_RL_EXEMPT = {"/healthz", "/readyz", "/docs", "/openapi.json", "/redoc"}


def _rate_limited(ip: str, now: float) -> bool:
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False
    with _rl_lock:
        hits = _rl_hits.setdefault(ip, deque())
        while hits and hits[0] <= now - 60.0:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False


def create_app() -> FastAPI:
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="GitHub Rising Radar API",
        version="0.1.0",
        description=(
            "Early detection of fast-rising GitHub repositories. "
            "Star velocity, acceleration, breakout scores and detection "
            "history for repos that are *starting* to trend — not the ones "
            "that already did."
        ),
        openapi_tags=[
            {"name": "repos", "description": "Repository list, detail, history, registration"},
            {"name": "rankings", "description": "Precomputed leaderboard snapshots"},
            {"name": "stats", "description": "Categories and service statistics"},
            {"name": "admin", "description": "Health probes"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def instrument(request: Request, call_next):  # type: ignore[no-untyped-def]
        api_metrics.record_call()
        path = request.url.path
        if path not in _RL_EXEMPT:
            client = request.client
            ip = client.host if client else "unknown"
            if _rate_limited(ip, time.monotonic()):
                return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": path})
            return JSONResponse(status_code=500, content={"detail": "internal server error"})
        dur_ms = round((time.perf_counter() - start) * 1000, 1)
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "dur_ms": dur_ms,
            },
        )
        return response

    app.include_router(admin.router)
    app.include_router(repos.router, prefix="/api")
    app.include_router(rankings.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": "github-rising-radar",
            "docs": "/docs",
            "health": "/healthz",
            "time": datetime.now(timezone.utc).isoformat(),
        }

    return app


app = create_app()
