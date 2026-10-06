"""Aggregate stats and category endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import metrics as api_metrics
from ..db import get_db
from ..models import Detection, Repository, RepositorySnapshot
from ..schemas import CategoryStat, StatsResponse

router = APIRouter(tags=["stats"])


@router.get(
    "/categories",
    response_model=list[CategoryStat],
    summary="Category counts",
    description="Number of tracked repositories per category, most common first.",
)
def list_categories(db: Session = Depends(get_db)) -> list[CategoryStat]:
    rows = (
        db.execute(
            select(Repository.category, func.count().label("cnt"))
            .where(Repository.category.is_not(None))
            .group_by(Repository.category)
            .order_by(func.count().desc())
        )
        .all()
    )
    return [CategoryStat(name=row[0], count=row[1]) for row in rows]


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Service stats",
    description=(
        "Tracked repos, snapshots in the last 24h, detections in the last 7d, "
        "and API calls in the last 24h (process-local counter, resets on restart)."
    ),
)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    now = datetime.now(timezone.utc)
    tracked = db.scalar(select(func.count()).select_from(Repository)) or 0
    snaps_24h = (
        db.scalar(
            select(func.count())
            .select_from(RepositorySnapshot)
            .where(RepositorySnapshot.ts >= now - timedelta(hours=24))
        )
        or 0
    )
    detections_7d = (
        db.scalar(
            select(func.count())
            .select_from(Detection)
            .where(Detection.first_detected_at >= now - timedelta(days=7))
        )
        or 0
    )
    return StatsResponse(
        tracked_repos=tracked,
        snapshots_24h=snaps_24h,
        detections_7d=detections_7d,
        api_calls_24h=api_metrics.calls_last_24h(now),
    )
