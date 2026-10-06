"""Liveness / readiness probes (mounted at the root, no /api prefix)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(tags=["admin"])


@router.get("/healthz", summary="Liveness probe")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    """200 when the database answers; 503 otherwise (container is not ready)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "database not ready") from exc
    return {"status": "ready", "db": "ok"}
